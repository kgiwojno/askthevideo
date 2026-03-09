/**
 * Cloudflare Worker — YouTube Transcript Proxy
 *
 * Fetches YouTube transcript data and returns it as JSON.
 * Uses YouTube's Innertube API with proper visitor data generation.
 *
 * Deploy to Cloudflare Workers (free tier: 100k requests/day).
 */

const INNERTUBE_API_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8";
const INNERTUBE_BASE = "https://www.youtube.com/youtubei/v1";

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
      return Response.json({ error: "POST only" }, { status: 405 });
    }

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

    // Debug mode: return diagnostic info
    if (body.debug) {
      return await debugFetch(videoId);
    }

    try {
      // Step 1: Hit the YouTube page to get visitorData and caption info
      const pageResp = await fetch(
        `https://www.youtube.com/watch?v=${videoId}&hl=en`,
        {
          headers: {
            "User-Agent":
              "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            Cookie: "CONSENT=PENDING+999; SOCS=CAESEwgDEgk2MTcxNjQxMjAaAmVuIAEaBgiA_LyaBg",
          },
          redirect: "follow",
        }
      );

      if (!pageResp.ok) {
        return Response.json(
          { error: `YouTube returned HTTP ${pageResp.status}` },
          { status: 502 }
        );
      }

      const html = await pageResp.text();

      // Check if we got a bot/consent page
      if (html.length < 50000 && !html.includes("ytInitialPlayerResponse")) {
        return Response.json(
          { error: "YouTube returned a consent/challenge page instead of video data" },
          { status: 502 }
        );
      }

      // Extract visitorData for authenticated Innertube calls
      const visitorMatch = html.match(/"visitorData"\s*:\s*"([^"]+)"/);
      const visitorData = visitorMatch ? visitorMatch[1] : null;

      // Try to extract caption tracks from the page
      const captionMatch = html.match(/"captionTracks"\s*:\s*(\[.+?\])\s*[,}]/);

      if (!captionMatch) {
        // Check if video exists but has no captions
        if (html.includes('"playabilityStatus":{"status":"ERROR"') ||
            html.includes('"playabilityStatus":{"status":"UNPLAYABLE"')) {
          return Response.json(
            { error: `Video ${videoId} is unavailable` },
            { status: 404 }
          );
        }
        return Response.json(
          { error: `No captions available for video ${videoId}` },
          { status: 404 }
        );
      }

      let captions;
      try {
        captions = JSON.parse(captionMatch[1]);
      } catch {
        return Response.json(
          { error: "Failed to parse caption tracks" },
          { status: 502 }
        );
      }

      if (!captions || captions.length === 0) {
        return Response.json(
          { error: `No captions available for video ${videoId}` },
          { status: 404 }
        );
      }

      // Prefer manual English, then auto English, then first
      let track =
        captions.find((c) => c.languageCode === "en" && c.kind !== "asr") ||
        captions.find((c) => c.languageCode === "en") ||
        captions[0];

      // Step 2: Fetch transcript using the baseUrl from caption track
      const transcriptUrl = track.baseUrl + "&fmt=json3";
      const transcriptResp = await fetch(transcriptUrl, {
        headers: {
          "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
          Cookie: "CONSENT=PENDING+999; SOCS=CAESEwgDEgk2MTcxNjQxMjAaAmVuIAEaBgiA_LyaBg",
        },
      });

      if (!transcriptResp.ok) {
        return Response.json(
          { error: `Transcript fetch failed with HTTP ${transcriptResp.status}` },
          { status: 502 }
        );
      }

      const transcriptText = await transcriptResp.text();

      let transcriptData;
      try {
        transcriptData = JSON.parse(transcriptText);
      } catch {
        return Response.json(
          { error: "YouTube returned non-JSON response for transcript" },
          { status: 502 }
        );
      }

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
        { headers: { "Access-Control-Allow-Origin": "*" } }
      );
    } catch (err) {
      return Response.json(
        { error: `Proxy error: ${err.message}` },
        { status: 500 }
      );
    }
  },
};

/**
 * Debug endpoint — returns diagnostic info about what YouTube returns
 */
async function debugFetch(videoId) {
  try {
    const resp = await fetch(
      `https://www.youtube.com/watch?v=${videoId}&hl=en`,
      {
        headers: {
          "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
          "Accept-Language": "en-US,en;q=0.9",
          Cookie: "CONSENT=PENDING+999; SOCS=CAESEwgDEgk2MTcxNjQxMjAaAmVuIAEaBgiA_LyaBg",
        },
        redirect: "follow",
      }
    );

    const html = await resp.text();
    const hasPlayerResponse = html.includes("ytInitialPlayerResponse");
    const hasCaptions = html.includes("captionTracks");
    const hasVisitorData = html.includes("visitorData");
    const playabilityMatch = html.match(/"playabilityStatus":\{"status":"(\w+)"/);

    return Response.json({
      status: resp.status,
      html_length: html.length,
      has_player_response: hasPlayerResponse,
      has_captions: hasCaptions,
      has_visitor_data: hasVisitorData,
      playability_status: playabilityMatch ? playabilityMatch[1] : "unknown",
      title_found: html.includes("<title>"),
      is_consent_page: html.includes("consent.youtube.com") || html.includes("CONSENT"),
      first_500_chars: html.substring(0, 500),
    });
  } catch (err) {
    return Response.json({ error: err.message }, { status: 500 });
  }
}
