/**
 * Cloudflare Worker — YouTube Transcript Proxy
 *
 * Fetches YouTube transcript data and returns it as JSON.
 * Uses a two-step approach: first gets video page for caption track URLs,
 * then fetches the transcript data directly.
 *
 * Deploy to Cloudflare Workers (free tier: 100k requests/day).
 *
 * Setup:
 *   1. Go to dash.cloudflare.com → Workers & Pages → Create
 *   2. Paste this code in the editor, Deploy
 *   3. Add secret: Settings → Variables → PROXY_SECRET = <your-secret>
 *   4. Set TRANSCRIPT_PROXY_URL and TRANSCRIPT_PROXY_SECRET in your app
 */

const BROWSER_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

const BROWSER_HEADERS = {
  "User-Agent": BROWSER_UA,
  "Accept-Language": "en-US,en;q=0.9",
  Accept:
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
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
      // Step 1: Fetch the timedtext list API to get available caption tracks
      const listUrl = `https://www.youtube.com/api/timedtext?v=${videoId}&type=list`;
      const listResp = await fetch(listUrl, { headers: BROWSER_HEADERS });

      if (!listResp.ok) {
        // Fallback: try the video page approach
        return await fetchViaVideoPage(videoId);
      }

      const listXml = await listResp.text();

      // Parse track info from XML
      // Format: <track id="0" name="" lang_code="en" lang_original="English" ... kind="asr"/>
      const tracks = [];
      const trackRegex =
        /<track\s+([^>]+)>/g;
      let match;
      while ((match = trackRegex.exec(listXml)) !== null) {
        const attrs = match[1];
        const lang = attrVal(attrs, "lang_code");
        const kind = attrVal(attrs, "kind");
        const name = attrVal(attrs, "lang_original") || lang;
        if (lang) {
          tracks.push({ lang, kind, name });
        }
      }

      if (tracks.length === 0) {
        // Try video page fallback
        return await fetchViaVideoPage(videoId);
      }

      // Prefer manual English, then auto English, then first
      let track =
        tracks.find((t) => t.lang === "en" && t.kind !== "asr") ||
        tracks.find((t) => t.lang === "en") ||
        tracks[0];

      // Step 2: Fetch the actual transcript
      let transcriptUrl = `https://www.youtube.com/api/timedtext?v=${videoId}&lang=${track.lang}&fmt=json3`;
      if (track.kind === "asr") {
        transcriptUrl += "&kind=asr";
      }

      const transcriptResp = await fetch(transcriptUrl, {
        headers: BROWSER_HEADERS,
      });

      if (!transcriptResp.ok) {
        return Response.json(
          {
            error: `Failed to fetch transcript (${transcriptResp.status})`,
          },
          { status: 502 }
        );
      }

      const transcriptData = await transcriptResp.json();
      return buildResponse(videoId, transcriptData, track);
    } catch (err) {
      return Response.json(
        { error: `Proxy error: ${err.message}` },
        { status: 500 }
      );
    }
  },
};

/**
 * Fallback: fetch transcript via video page HTML parsing
 */
async function fetchViaVideoPage(videoId) {
  const pageResp = await fetch(
    `https://www.youtube.com/watch?v=${videoId}`,
    {
      headers: BROWSER_HEADERS,
      redirect: "follow",
    }
  );

  if (!pageResp.ok) {
    return Response.json(
      { error: `YouTube returned ${pageResp.status}` },
      { status: 502 }
    );
  }

  const html = await pageResp.text();

  // Check availability
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
    /ytInitialPlayerResponse\s*=\s*(\{.+?\});\s*var\s/
  );
  if (!playerMatch) {
    // Try alternate pattern
    const altMatch = html.match(
      /ytInitialPlayerResponse\s*=\s*(\{.+?\});/
    );
    if (!altMatch) {
      return Response.json(
        { error: "Could not parse video page" },
        { status: 502 }
      );
    }
    return extractFromPlayerResponse(altMatch[1], videoId);
  }
  return extractFromPlayerResponse(playerMatch[1], videoId);
}

async function extractFromPlayerResponse(jsonStr, videoId) {
  let playerResponse;
  try {
    playerResponse = JSON.parse(jsonStr);
  } catch {
    return Response.json(
      { error: "Failed to parse player JSON" },
      { status: 502 }
    );
  }

  const captions =
    playerResponse?.captions?.playerCaptionsTracklistRenderer?.captionTracks;
  if (!captions || captions.length === 0) {
    return Response.json(
      { error: `No captions available for video ${videoId}` },
      { status: 404 }
    );
  }

  let track =
    captions.find((c) => c.languageCode === "en" && c.kind !== "asr") ||
    captions.find((c) => c.languageCode === "en") ||
    captions[0];

  const transcriptResp = await fetch(track.baseUrl + "&fmt=json3", {
    headers: BROWSER_HEADERS,
  });

  if (!transcriptResp.ok) {
    return Response.json(
      { error: `Failed to fetch transcript data (${transcriptResp.status})` },
      { status: 502 }
    );
  }

  const transcriptData = await transcriptResp.json();
  return buildResponse(
    videoId,
    transcriptData,
    {
      lang: track.languageCode,
      kind: track.kind || "",
      name: track.name?.simpleText || track.languageCode,
    }
  );
}

function buildResponse(videoId, transcriptData, track) {
  const snippets = (transcriptData.events || [])
    .filter((e) => e.segs && e.tStartMs !== undefined)
    .map((e) => ({
      text: (e.segs || []).map((s) => s.utf8 || "").join(""),
      start: e.tStartMs / 1000,
      duration: (e.dDurationMs || 0) / 1000,
    }))
    .filter((s) => s.text.trim() !== "");

  if (snippets.length === 0) {
    return Response.json({ error: "Transcript is empty" }, { status: 404 });
  }

  const lastSnippet = snippets[snippets.length - 1];

  return Response.json(
    {
      video_id: videoId,
      language: track.name || track.lang || "unknown",
      language_code: track.lang,
      is_generated: track.kind === "asr",
      snippets: snippets,
      duration_seconds: lastSnippet.start + lastSnippet.duration,
    },
    { headers: { "Access-Control-Allow-Origin": "*" } }
  );
}

function attrVal(attrs, name) {
  const m = attrs.match(new RegExp(`${name}="([^"]*)"`));
  return m ? m[1] : "";
}
