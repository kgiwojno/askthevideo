/**
 * Cloudflare Worker — YouTube Transcript Proxy
 *
 * Uses YouTube's Innertube API with the Android client (same as youtube_transcript_api)
 * to fetch transcripts. The Android client returns captions without restrictions.
 *
 * Deploy to Cloudflare Workers (free tier: 100k requests/day).
 *
 * Setup:
 *   1. Go to dash.cloudflare.com → Workers & Pages → Create
 *   2. Paste this code in the editor, Deploy
 *   3. Add secret: Settings → Variables → PROXY_SECRET = <your-secret>
 *   4. Set TRANSCRIPT_PROXY_URL and TRANSCRIPT_PROXY_SECRET in your app
 */

const INNERTUBE_CONTEXT = {
  client: {
    clientName: "ANDROID",
    clientVersion: "20.10.38",
  },
};

export default {
  async fetch(request, env) {
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
      return jsonErr("POST only", 405);
    }

    const authHeader = request.headers.get("Authorization") || "";
    const token = authHeader.replace("Bearer ", "");
    if (env.PROXY_SECRET && token !== env.PROXY_SECRET) {
      return jsonErr("Unauthorized", 401);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return jsonErr("Invalid JSON", 400);
    }

    const videoId = body.video_id;
    if (!videoId || typeof videoId !== "string") {
      return jsonErr("video_id required", 400);
    }

    try {
      // Step 1: Get video page to extract the API key
      const pageResp = await fetch(
        `https://www.youtube.com/watch?v=${videoId}&hl=en`,
        {
          headers: {
            "User-Agent": "Mozilla/5.0",
            Cookie: "CONSENT=PENDING+999",
          },
          redirect: "follow",
        }
      );

      if (!pageResp.ok) {
        return jsonErr(`YouTube returned HTTP ${pageResp.status}`, 502);
      }

      const html = await pageResp.text();
      const apiKeyMatch = html.match(/"INNERTUBE_API_KEY":\s*"([a-zA-Z0-9_-]+)"/);
      const apiKey = apiKeyMatch
        ? apiKeyMatch[1]
        : "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8";

      // Step 2: Call Innertube player API with Android client
      const playerResp = await fetch(
        `https://www.youtube.com/youtubei/v1/player?key=${apiKey}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            context: INNERTUBE_CONTEXT,
            videoId: videoId,
          }),
        }
      );

      if (!playerResp.ok) {
        return jsonErr(`Innertube API returned HTTP ${playerResp.status}`, 502);
      }

      const playerData = await playerResp.json();

      // Check playability
      const status = playerData?.playabilityStatus?.status;
      if (status === "ERROR" || status === "UNPLAYABLE") {
        const reason =
          playerData?.playabilityStatus?.reason || `Video ${videoId} is unavailable`;
        return jsonErr(reason, 404);
      }

      const captions =
        playerData?.captions?.playerCaptionsTracklistRenderer?.captionTracks;
      if (!captions || captions.length === 0) {
        return jsonErr(`No captions available for video ${videoId}`, 404);
      }

      // Prefer manual English → auto English → first available
      const track =
        captions.find((c) => c.languageCode === "en" && c.kind !== "asr") ||
        captions.find((c) => c.languageCode === "en") ||
        captions[0];

      // Step 3: Fetch transcript from the baseUrl
      // Remove &exp=xpe if present (requires special handling)
      let transcriptUrl = track.baseUrl;

      const transcriptResp = await fetch(transcriptUrl, {
        headers: { "User-Agent": "Mozilla/5.0" },
      });

      if (!transcriptResp.ok) {
        return jsonErr(
          `Transcript fetch failed with HTTP ${transcriptResp.status}`,
          502
        );
      }

      const transcriptText = await transcriptResp.text();

      // The baseUrl returns XML by default, parse it
      const snippets = parseTranscriptXml(transcriptText);

      if (snippets.length === 0) {
        // Try JSON format as fallback
        const jsonResp = await fetch(transcriptUrl + "&fmt=json3", {
          headers: { "User-Agent": "Mozilla/5.0" },
        });
        if (jsonResp.ok) {
          const jsonText = await jsonResp.text();
          try {
            const jsonData = JSON.parse(jsonText);
            const jsonSnippets = parseTranscriptJson(jsonData);
            if (jsonSnippets.length > 0) {
              return buildSuccess(videoId, jsonSnippets, track);
            }
          } catch {}
        }
        return jsonErr("Transcript is empty", 404);
      }

      return buildSuccess(videoId, snippets, track);
    } catch (err) {
      return jsonErr(`Proxy error: ${err.message}`, 500);
    }
  },
};

/** Parse transcript XML format: <text start="0" dur="1.5">Hello</text> */
function parseTranscriptXml(xml) {
  const snippets = [];
  const regex = /<text\s+start="([\d.]+)"\s+dur="([\d.]+)"[^>]*>([\s\S]*?)<\/text>/g;
  let match;
  while ((match = regex.exec(xml)) !== null) {
    const text = decodeHtmlEntities(match[3]).trim();
    if (text) {
      snippets.push({
        text,
        start: parseFloat(match[1]),
        duration: parseFloat(match[2]),
      });
    }
  }
  return snippets;
}

/** Parse transcript JSON3 format */
function parseTranscriptJson(data) {
  return (data.events || [])
    .filter((e) => e.segs && e.tStartMs !== undefined)
    .map((e) => ({
      text: (e.segs || []).map((s) => s.utf8 || "").join(""),
      start: e.tStartMs / 1000,
      duration: (e.dDurationMs || 0) / 1000,
    }))
    .filter((s) => s.text.trim() !== "");
}

function decodeHtmlEntities(str) {
  return str
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\n/g, " ");
}

function buildSuccess(videoId, snippets, track) {
  const last = snippets[snippets.length - 1];
  return Response.json(
    {
      video_id: videoId,
      language: track.name?.simpleText || track.languageCode || "unknown",
      language_code: track.languageCode,
      is_generated: track.kind === "asr",
      snippets,
      duration_seconds: last.start + last.duration,
    },
    { headers: { "Access-Control-Allow-Origin": "*" } }
  );
}

function jsonErr(msg, status) {
  return Response.json({ error: msg }, { status });
}
