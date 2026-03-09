/**
 * Cloudflare Worker — YouTube Transcript Proxy
 *
 * Fetches YouTube transcript data and returns it as JSON.
 * Deploy to Cloudflare Workers (free tier: 100k requests/day).
 *
 * Setup:
 *   1. Go to dash.cloudflare.com → Workers & Pages → Create
 *   2. Name it "youtube-transcript" (or similar)
 *   3. Paste this code in the editor
 *   4. Deploy
 *   5. Add a secret: Settings → Variables → PROXY_SECRET = <your-secret>
 *   6. Copy the worker URL (e.g. https://youtube-transcript.yourname.workers.dev)
 *   7. Set TRANSCRIPT_PROXY_URL=<worker-url> and TRANSCRIPT_PROXY_SECRET=<secret> in Koyeb
 */

const INNERTUBE_URL = "https://www.youtube.com/youtubei/v1/get_transcript";
const INNERTUBE_CLIENT = {
  clientName: "WEB",
  clientVersion: "2.20240313.05.00",
};

export default {
  async fetch(request, env) {
    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "POST",
          "Access-Control-Allow-Headers": "Content-Type, Authorization",
        },
      });
    }

    if (request.method !== "POST") {
      return Response.json({ error: "POST only" }, { status: 405 });
    }

    // Auth check
    const authHeader = request.headers.get("Authorization") || "";
    const token = authHeader.replace("Bearer ", "");
    if (env.PROXY_SECRET && token !== env.PROXY_SECRET) {
      return Response.json({ error: "Unauthorized" }, { status: 401 });
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return Response.json({ error: "Invalid JSON" }, { status: 400 });
    }

    const videoId = body.video_id;
    if (!videoId || typeof videoId !== "string") {
      return Response.json({ error: "video_id required" }, { status: 400 });
    }

    try {
      // Step 1: Fetch the video page to get serialized player data
      const pageResp = await fetch(
        `https://www.youtube.com/watch?v=${videoId}`,
        {
          headers: {
            "User-Agent":
              "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
          },
        }
      );

      if (!pageResp.ok) {
        return Response.json(
          { error: `YouTube returned ${pageResp.status}` },
          { status: 502 }
        );
      }

      const html = await pageResp.text();

      // Check if video is available
      if (
        html.includes('"playabilityStatus":{"status":"ERROR"') ||
        html.includes('"playabilityStatus":{"status":"UNPLAYABLE"')
      ) {
        return Response.json(
          { error: `Video ${videoId} is unavailable` },
          { status: 404 }
        );
      }

      // Extract captions from ytInitialPlayerResponse
      const playerMatch = html.match(
        /ytInitialPlayerResponse\s*=\s*(\{.+?\});/
      );
      if (!playerMatch) {
        return Response.json(
          { error: "Could not parse player response" },
          { status: 502 }
        );
      }

      let playerResponse;
      try {
        playerResponse = JSON.parse(playerMatch[1]);
      } catch {
        return Response.json(
          { error: "Failed to parse player JSON" },
          { status: 502 }
        );
      }

      const captions =
        playerResponse?.captions?.playerCaptionsTracklistRenderer
          ?.captionTracks;
      if (!captions || captions.length === 0) {
        return Response.json(
          { error: `No captions available for video ${videoId}` },
          { status: 404 }
        );
      }

      // Prefer manual captions in English, fall back to auto-generated, then first available
      let track =
        captions.find((c) => c.languageCode === "en" && c.kind !== "asr") ||
        captions.find((c) => c.languageCode === "en") ||
        captions[0];

      // Step 2: Fetch the actual transcript XML
      const transcriptResp = await fetch(track.baseUrl + "&fmt=json3");

      if (!transcriptResp.ok) {
        return Response.json(
          { error: "Failed to fetch transcript data" },
          { status: 502 }
        );
      }

      const transcriptData = await transcriptResp.json();

      // Parse events into snippets
      const snippets = (transcriptData.events || [])
        .filter((e) => e.segs && e.tStartMs !== undefined)
        .map((e) => ({
          text: (e.segs || []).map((s) => s.utf8 || "").join(""),
          start: e.tStartMs / 1000,
          duration: (e.dDurationMs || 0) / 1000,
        }))
        .filter((s) => s.text.trim() !== "");

      if (snippets.length === 0) {
        return Response.json(
          { error: "Transcript is empty" },
          { status: 404 }
        );
      }

      const lastSnippet = snippets[snippets.length - 1];

      return Response.json(
        {
          video_id: videoId,
          language: track.name?.simpleText || track.languageCode || "unknown",
          language_code: track.languageCode,
          is_generated: track.kind === "asr",
          snippets: snippets,
          duration_seconds: lastSnippet.start + lastSnippet.duration,
        },
        {
          headers: {
            "Access-Control-Allow-Origin": "*",
          },
        }
      );
    } catch (err) {
      return Response.json(
        { error: `Proxy error: ${err.message}` },
        { status: 500 }
      );
    }
  },
};
