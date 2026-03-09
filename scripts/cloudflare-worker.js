/**
 * Cloudflare Worker — YouTube Transcript Proxy
 *
 * Uses YouTube's Innertube get_transcript API to fetch transcripts entirely
 * through the API (no separate timedtext fetch). This avoids YouTube blocking
 * the timedtext endpoint from cloud IPs.
 *
 * Deploy to Cloudflare Workers (free tier: 100k requests/day).
 *
 * Setup:
 *   1. Go to dash.cloudflare.com → Workers & Pages → Create
 *   2. Paste this code in the editor, Deploy
 *   3. Add secret: Settings → Variables → PROXY_SECRET = <your-secret>
 *   4. Set TRANSCRIPT_PROXY_URL and TRANSCRIPT_PROXY_SECRET in your app
 */

const WEB_CONTEXT = {
  client: {
    clientName: "WEB",
    clientVersion: "2.20240313.05.00",
  },
};

const ANDROID_CONTEXT = {
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
      // Step 1: Get video page to extract API key and serialized share entity (for get_transcript)
      const pageResp = await fetch(
        `https://www.youtube.com/watch?v=${videoId}&hl=en`,
        {
          headers: {
            "User-Agent":
              "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            Cookie: "CONSENT=PENDING+999",
          },
          redirect: "follow",
        }
      );

      if (!pageResp.ok) {
        return jsonErr(`YouTube returned HTTP ${pageResp.status}`, 502);
      }

      const html = await pageResp.text();

      // Extract API key
      const apiKeyMatch = html.match(
        /"INNERTUBE_API_KEY":\s*"([a-zA-Z0-9_-]+)"/
      );
      const apiKey = apiKeyMatch
        ? apiKeyMatch[1]
        : "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8";

      // Step 2: Try get_transcript API first (works even when player API says UNPLAYABLE)
      const transcriptResult = await tryGetTranscript(apiKey, videoId, "en");
      if (transcriptResult) {
        return buildSuccess(videoId, transcriptResult, { languageCode: "en", kind: "asr" });
      }

      // Step 3: Use player API with Android client to get caption tracks + baseUrl
      let captions = null;
      let track = null;

      const playerResp = await fetch(
        `https://www.youtube.com/youtubei/v1/player?key=${apiKey}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            context: ANDROID_CONTEXT,
            videoId: videoId,
          }),
        }
      );

      if (playerResp.ok) {
        const playerData = await playerResp.json();

        // Only hard-fail on ERROR status (not UNPLAYABLE — captions may still exist)
        const playStatus = playerData?.playabilityStatus?.status;
        if (playStatus === "ERROR") {
          const reason =
            playerData?.playabilityStatus?.reason ||
            `Video ${videoId} is unavailable`;
          return jsonErr(reason, 404);
        }

        captions =
          playerData?.captions?.playerCaptionsTracklistRenderer?.captionTracks;
        if (captions && captions.length > 0) {
          track =
            captions.find((c) => c.languageCode === "en" && c.kind !== "asr") ||
            captions.find((c) => c.languageCode === "en") ||
            captions[0];
        }
      }

      // Step 4: If we got a track with baseUrl, try fetching it
      if (track?.baseUrl) {
        const baseUrlResult = await tryBaseUrl(track.baseUrl);
        if (baseUrlResult && baseUrlResult.length > 0) {
          return buildSuccess(videoId, baseUrlResult, track);
        }
      }

      // Step 5: Fallback — try constructing timedtext URL manually
      const lang = track?.languageCode || "en";
      const manualResult = await tryManualTimedtext(videoId, lang);
      if (manualResult && manualResult.length > 0) {
        return buildSuccess(videoId, manualResult, track || { languageCode: lang, kind: "asr" });
      }

      return jsonErr(
        `No captions available for video ${videoId}`,
        404
      );
    } catch (err) {
      return jsonErr(`Proxy error: ${err.message}`, 500);
    }
  },
};

/**
 * Try the Innertube get_transcript endpoint.
 * This returns transcript data directly in the API response.
 */
async function tryGetTranscript(apiKey, videoId, langCode) {
  try {
    const resp = await fetch(
      `https://www.youtube.com/youtubei/v1/get_transcript?key=${apiKey}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          context: WEB_CONTEXT,
          params: buildTranscriptParams(videoId),
        }),
      }
    );

    if (!resp.ok) return null;

    const data = await resp.json();

    // Navigate the response structure
    const renderer =
      data?.actions?.[0]?.updateEngagementPanelAction?.content
        ?.transcriptRenderer?.body?.transcriptBodyRenderer;
    if (!renderer) return null;

    const cueGroups = renderer.cueGroups;
    if (!cueGroups || cueGroups.length === 0) return null;

    const snippets = [];
    for (const group of cueGroups) {
      const cues =
        group.transcriptCueGroupRenderer?.cues;
      if (!cues) continue;
      for (const cue of cues) {
        const r = cue.transcriptCueRenderer;
        if (!r) continue;
        const text = (r.cue?.simpleText || "").trim();
        const startMs = parseInt(r.startOffsetMs || "0", 10);
        const durationMs = parseInt(r.durationMs || "0", 10);
        if (text) {
          snippets.push({
            text,
            start: startMs / 1000,
            duration: durationMs / 1000,
          });
        }
      }
    }

    return snippets.length > 0 ? snippets : null;
  } catch {
    return null;
  }
}

/**
 * Build the protobuf-like params for get_transcript.
 * This encodes the video ID in the format YouTube expects.
 */
function buildTranscriptParams(videoId) {
  // The params field is a base64-encoded protobuf message.
  // Structure: field 1 (string) = "\n" + videoId
  // This is the same encoding youtube_transcript_api uses.
  const inner = "\n" + videoId;
  const outer = "\x12" + String.fromCharCode(inner.length) + inner;
  return btoa(outer);
}

/**
 * Fallback: fetch transcript from baseUrl with proper headers
 */
async function tryBaseUrl(baseUrl) {
  if (!baseUrl) return null;
  try {
    const resp = await fetch(baseUrl, {
      headers: {
        "User-Agent":
          "com.google.android.youtube/20.10.38 (Linux; U; Android 14; en_US)",
        "Accept-Language": "en-US,en;q=0.9",
      },
    });
    if (!resp.ok) return null;
    const text = await resp.text();
    if (!text || text.length < 50) return null;
    const snippets = parseTranscriptXml(text);
    if (snippets.length > 0) return snippets;

    // Try JSON format
    const jsonResp = await fetch(baseUrl + "&fmt=json3", {
      headers: {
        "User-Agent":
          "com.google.android.youtube/20.10.38 (Linux; U; Android 14; en_US)",
      },
    });
    if (!jsonResp.ok) return null;
    const jsonText = await jsonResp.text();
    try {
      const jsonData = JSON.parse(jsonText);
      return parseTranscriptJson(jsonData);
    } catch {
      return null;
    }
  } catch {
    return null;
  }
}

/**
 * Fallback: construct timedtext URL manually
 */
async function tryManualTimedtext(videoId, lang) {
  try {
    const url = `https://www.youtube.com/api/timedtext?v=${videoId}&lang=${lang || "en"}&fmt=json3`;
    const resp = await fetch(url, {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
      },
    });
    if (!resp.ok) return null;
    const text = await resp.text();
    if (!text || text.length < 50) return null;
    try {
      const data = JSON.parse(text);
      return parseTranscriptJson(data);
    } catch {
      // Maybe XML
      return parseTranscriptXml(text);
    }
  } catch {
    return null;
  }
}

/** Parse transcript XML format: <text start="0" dur="1.5">Hello</text> */
function parseTranscriptXml(xml) {
  const snippets = [];
  // Handle both <text> (standard) and <p> (timedtext format 3) tags
  const regex =
    /<(?:text|p)\s+(?:start|t)="([\d.]+)"\s+(?:dur|d)="([\d.]+)"[^>]*>([\s\S]*?)<\/(?:text|p)>/g;
  let match;
  while ((match = regex.exec(xml)) !== null) {
    let startVal = parseFloat(match[1]);
    let durVal = parseFloat(match[2]);
    const text = decodeHtmlEntities(match[3]).trim();
    // <p t="..." d="..."> uses milliseconds
    if (match[0].startsWith("<p")) {
      startVal = startVal / 1000;
      durVal = durVal / 1000;
    }
    if (text) {
      snippets.push({ text, start: startVal, duration: durVal });
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
