/**
 * Cloudflare Worker — YouTube Transcript Proxy
 *
 * Fetches YouTube transcript data and returns it as JSON.
 * Deploy to Cloudflare Workers (free tier: 100k requests/day).
 *
 * Setup:
 *   1. Go to dash.cloudflare.com → Workers & Pages → Create
 *   2. Paste this code in the editor, Deploy
 *   3. Add secret: Settings → Variables → PROXY_SECRET = <your-secret>
 *   4. Set TRANSCRIPT_PROXY_URL and TRANSCRIPT_PROXY_SECRET in your app
 */

const COOKIES =
  "CONSENT=PENDING+999; SOCS=CAESEwgDEgk2MTcxNjQxMjAaAmVuIAEaBgiA_LyaBg";

const HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
  "Accept-Language": "en-US,en;q=0.9",
  Cookie: COOKIES,
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

    try {
      // Step 1: Fetch video page to get caption track URLs
      const pageResp = await fetch(
        `https://www.youtube.com/watch?v=${videoId}&hl=en`,
        { headers: HEADERS, redirect: "follow" }
      );

      if (!pageResp.ok) {
        return jsonErr(`YouTube returned HTTP ${pageResp.status}`, 502);
      }

      const html = await pageResp.text();

      if (!html.includes("ytInitialPlayerResponse")) {
        return jsonErr(
          "YouTube returned a consent/challenge page instead of video data",
          502
        );
      }

      // Check video availability
      if (
        html.includes('"playabilityStatus":{"status":"ERROR"') ||
        html.includes('"playabilityStatus":{"status":"UNPLAYABLE"')
      ) {
        return jsonErr(`Video ${videoId} is unavailable`, 404);
      }

      // Extract captionTracks array using bracket matching
      // (regex fails because URLs inside contain special chars)
      const captions = extractJsonArray(html, '"captionTracks":');

      if (!captions || captions.length === 0) {
        return jsonErr(`No captions available for video ${videoId}`, 404);
      }

      // Prefer manual English → auto English → first available
      const track =
        captions.find((c) => c.languageCode === "en" && c.kind !== "asr") ||
        captions.find((c) => c.languageCode === "en") ||
        captions[0];

      // Step 2: Fetch the transcript JSON
      const transcriptResp = await fetch(track.baseUrl + "&fmt=json3", {
        headers: HEADERS,
      });

      if (!transcriptResp.ok) {
        return jsonErr(
          `Transcript fetch failed with HTTP ${transcriptResp.status}`,
          502
        );
      }

      const transcriptText = await transcriptResp.text();

      let transcriptData;
      try {
        transcriptData = JSON.parse(transcriptText);
      } catch {
        return jsonErr(
          "YouTube returned non-JSON response for transcript",
          502
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
        return jsonErr("Transcript is empty", 404);
      }

      const last = snippets[snippets.length - 1];

      return Response.json(
        {
          video_id: videoId,
          language:
            track.name?.simpleText || track.languageCode || "unknown",
          language_code: track.languageCode,
          is_generated: track.kind === "asr",
          snippets,
          duration_seconds: last.start + last.duration,
        },
        { headers: { "Access-Control-Allow-Origin": "*" } }
      );
    } catch (err) {
      return jsonErr(`Proxy error: ${err.message}`, 500);
    }
  },
};

/** Find a JSON array in a string after a given marker, using bracket matching. */
function extractJsonArray(text, marker) {
  const start = text.indexOf(marker);
  if (start === -1) return null;

  const arrStart = text.indexOf("[", start);
  if (arrStart === -1) return null;

  let depth = 0;
  for (let i = arrStart; i < text.length && i < arrStart + 100000; i++) {
    if (text[i] === "[") depth++;
    else if (text[i] === "]") depth--;
    if (depth === 0) {
      try {
        return JSON.parse(text.substring(arrStart, i + 1));
      } catch {
        return null;
      }
    }
  }
  return null;
}

function jsonErr(msg, status) {
  return Response.json({ error: msg }, { status });
}
