// 부자알람 — 텔레그램 웹훅 → GitHub Actions 즉시 트리거 (Cloudflare Workers)
//
// 왜 필요한가:
//   GitHub Actions의 `schedule` 크론은 무료 티어에서 심하게 지연된다.
//   실측(2026-07-26): 15분으로 설정했는데 실제 간격이 62·71·105·68·95분.
//   반면 `repository_dispatch`로 트리거하면 수초~1분 내에 시작한다.
//   그래서 텔레그램 → Worker → repository_dispatch 경로를 만들어 명령을 즉시 처리한다.
//
// 동작:
//   1) 텔레그램이 이 Worker로 업데이트를 POST
//   2) Worker가 즉시 "접수" 메시지를 보내 사용자에게 반응(체감 지연 0)
//   3) GitHub repository_dispatch 발사 — 업데이트 원문을 client_payload로 전달
//   4) run.py가 그 payload 하나만 처리 (getUpdates 호출 안 함)
//
// 필요한 환경변수(Worker Settings → Variables and Secrets):
//   TELEGRAM_TOKEN   봇 토큰
//   GH_TOKEN         GitHub PAT (Fine-grained: 대상 레포 Contents=Read and write)
//                    ※ repository_dispatch는 쓰기 권한이 필요하다. 읽기전용으로
//                       만들면 dispatch가 403으로 죽는다(run.yml에서 permissions:
//                       contents: write를 빠뜨려 같은 403을 이미 한 번 겪었다).
//   GH_REPO          "pcy604/buza-bot"
//   WEBHOOK_SECRET   임의 문자열 — 텔레그램 setWebhook의 secret_token과 동일해야 함

const ACK = {
  // /report는 이미 만든 종목이면 30초쯤, 처음 보는 종목이면 자료 생성부터 해서
  // 3~5분 걸린다. 어느 쪽인지는 봇이 판정 후 따로 알려주므로 여기선 뭉뚱그린다.
  '/report': '📊 12장 리포트 준비 시작했어요.',
  '/ir': '📑 IR 다이제스트 생성 시작했어요.',
  '/yt': '🎬 영상 요약 시작했어요.',
  '/watch': '👁️ 감시 등록 중이에요. (20초쯤 걸려요)',
};

// 인자 없이 누른 명령(☰ 메뉴) → 여기서 바로 사용법을 '답장 모드'로 보내고 GitHub 은 안 깨운다.
// 사용자가 그 메시지에 답장하면(예: 'TSLA') 봇이 '/dd TSLA' 로 처리한다(bot.py USAGE 와 같은 표).
const USAGE = {
  '/watch':   ['👁️ /watch 감시 등록 — 종목을 답장으로 보내 주세요\n예: TSLA · 삼성전자 · 005930', 'TSLA · 삼성전자'],
  '/unwatch': ['🗑️ /unwatch 감시 해제 — 종목을 답장으로 보내 주세요\n목록은 /watchlist', 'TSLA · 삼성전자'],
  '/report':  ['📑 /report 심층 리포트 — 미국 티커를 답장으로 보내 주세요\n예: TSLA · NVDA (한국 종목 리포트는 개선 중 — 한국은 /dashboard 삼성전자)', 'TSLA · NVDA'],
  '/ir':      ['📡 /ir 공시·분기 재무 — 미국 티커를 답장으로 보내 주세요\n예: TSLA', 'TSLA'],
  '/yt':      ['🎬 /yt 영상 요약 — 유튜브 링크를 답장으로 보내 주세요\n(링크만 그냥 보내도 돼요)', 'https://youtu.be/…'],
  '/add':     ['➕ /add 채널 구독 — 유튜브 채널 주소를 답장으로 보내 주세요\n예: https://youtube.com/@채널이름', 'https://youtube.com/@…'],
  '/person':  ['🧑 /person 인물 영상 — 이름을 답장으로 보내 주세요\n예: 박세익', '박세익'],
  '/remove':  ['➖ /remove 구독 해제 — /list 의 번호를 답장으로 보내 주세요', '1'],
};
const USAGE_EN = {
  '/watch': '👁️ /watch — reply with a ticker\ne.g. TSLA · 005930', '/unwatch': '🗑️ /unwatch — reply with a ticker',
  '/report': '📑 /report — reply with a ticker\ne.g. TSLA', '/ir': '📡 /ir — reply with a US ticker\ne.g. TSLA',
  '/yt': '🎬 /yt — reply with a YouTube link',
  '/add': '➕ /add — reply with a YouTube channel URL', '/person': '🧑 /person — reply with a name',
  '/remove': '➖ /remove — reply with the number from /list',
};

function tgSend(env, body) {
  return fetch(`https://api.telegram.org/bot${env.TELEGRAM_TOKEN}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).catch(() => {});
}

// ── 장 마감 시황 정시 실행 (2026-10-21) ──────────────────────────────────
// GitHub Actions schedule 은 2~3시간씩 밀린다(10-22 06:30 KST 미국 리포트가 08:40 까지 안 돌았다).
// Cloudflare Cron Trigger 는 정시에 돈다 → 여기서 깨운다. GitHub schedule 은 예비로 남겨 둔다(중복은 무해).
//   ① 대시보드 market-report 워크플로 실행(리포트 생성, 2~3분) → ② 10분 뒤 봇에 '발송' 신호.
// 크론 식은 UTC. wrangler.toml [triggers] 와 같아야 한다.
// 2026-10-24 개편: 크론 하나(10분마다)로 돌고, 무엇을 할지는 아래 표(UTC 시각·요일)로 정한다.
//   ① 예전 '1-5' 는 Cloudflare 에서 **일~목**이었다(Cloudflare 요일은 1=일요일). 그래서 금요일(10-23)
//      한국 장·미국 장 시황이 통째로 안 돌았다. 여기서는 JS getUTCDay()(0=일) 로 직접 판정한다.
//   ② 무료 플랜 크론 트리거는 워커당 5개가 상한이라, 시각마다 크론을 늘리는 방식은 막힌다.
//   ③ 리포트 생성이 늦어도 놓치지 않게 봇 발송 신호를 30분 간격으로 3번 보낸다(같은 장은 1회만 감).
//   ④ 뉴스 요약 시각(KST 08·20시)에도 봇을 깨운다 — GitHub schedule 은 2~4시간씩 밀린다.
const WEEKDAY = [1, 2, 3, 4, 5];          // 월~금 (getUTCDay: 0=일)
const EVERY = [0, 1, 2, 3, 4, 5, 6];

// 2026-11-06 차니 요청: 시황을 더 일찍. 미국 장 마감은 서머타임이면 20:00 UTC(KST 05:00), 아니면 21:00 UTC(06:00).
//   예전엔 둘 다 21:30 UTC 고정(겨울 +30분·여름 +90분 대기). 이제 마감 10분 뒤 생성 → 5분 뒤부터 발송 신호.
//   대시보드 생성 1분 남짓 + 봇은 GitHub API 로 캐시 없이 읽으므로 보통 마감 +20분 안팎에 도착.
//   미국 DST: 3월 둘째 일요일 07:00 UTC ~ 11월 첫째 일요일 06:00 UTC.
function nthSunday(y, m, n) {            // m: 0=1월
  const d = new Date(Date.UTC(y, m, 1));
  const first = (7 - d.getUTCDay()) % 7 + 1;
  return first + 7 * (n - 1);
}
function usDst(now) {
  const y = now.getUTCFullYear();
  const start = Date.UTC(y, 2, nthSunday(y, 2, 2), 7);
  const end = Date.UTC(y, 10, nthSunday(y, 10, 1), 6);
  return now.getTime() >= start && now.getTime() < end;
}
// 2026-11-20: 유럽(바르샤바) 서머타임 — 3월·10월 마지막 일요일 01:00 UTC. 예전엔 06/07·18/19시를 둘 다 깨워 하루 2회가 헛돌았다.
function euDst(now) {
  const y = now.getUTCFullYear();
  const last = (mo) => { const d = new Date(Date.UTC(y, mo + 1, 0)); return d.getUTCDate() - d.getUTCDay(); };
  return now.getTime() >= Date.UTC(y, 2, last(2), 1) && now.getTime() < Date.UTC(y, 9, last(9), 1);
}
function hhmm(h, m) { return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`; }

function plan(now) {
  const c = usDst(now) ? 20 : 21;        // 미국 장 마감(UTC 시)
  return [
    { at: hhmm(c, 10), days: WEEKDAY, dash: 'daily' },   // 마감 +10분 생성(그날 미국 장, 월~금)
    { at: hhmm(c, 15), days: WEEKDAY, bot: 'market' },
    { at: hhmm(c, 20), days: WEEKDAY, bot: 'market' },
    { at: hhmm(c, 30), days: WEEKDAY, bot: 'market' },
    { at: hhmm(c + 1, 0), days: WEEKDAY, bot: 'market' },
    { at: '06:45', days: WEEKDAY, dash: 'kr' },          // KST 15:45 — 한국 장 마감 15:30 +15분(KRX 종목 등락 반영 대기)
    // 2026-11-24 재시도 — 대시보드가 '종목 시세가 아직 종가가 아님'(장중 스냅샷)이면 발행을 미룬다. 16:30 이 마지막.
    { at: '07:00', days: WEEKDAY, dash: 'kr' },
    { at: '07:15', days: WEEKDAY, dash: 'kr' },
    { at: '07:30', days: WEEKDAY, dash: 'kr' },
    { at: '06:50', days: WEEKDAY, bot: 'market' },
    { at: '06:55', days: WEEKDAY, bot: 'market' },
    { at: '07:05', days: WEEKDAY, bot: 'market' },
    { at: '07:20', days: WEEKDAY, bot: 'market' },
    { at: '07:35', days: WEEKDAY, bot: 'market' },
    { at: '23:00', days: EVERY, bot: 'tick' },           // KST 08:00 — 뉴스 요약·주기 작업
    { at: '11:00', days: EVERY, bot: 'tick' },           // KST 20:00
    // 유럽(바르샤바) 사용자 08·20시 — 서머타임(UTC+2) 06·18시 / 겨울(UTC+1) 07·19시
    { at: euDst(now) ? '06:00' : '07:10', days: EVERY, bot: 'tick' },   // 07:10 = 07:05 시황 재시도와 안 겹치게
    { at: euDst(now) ? '18:00' : '19:00', days: EVERY, bot: 'tick' },
  ];
}

function due(now) {
  const m = now.getUTCMinutes() - now.getUTCMinutes() % 5;   // 크론 5분 간격
  const hm = hhmm(now.getUTCHours(), m);
  return plan(now).filter(p => p.at === hm && p.days.includes(now.getUTCDay()));
}

async function gh(env, path, body) {
  const r = await fetch(`https://api.github.com/repos/${path}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${(env.GH_TOKEN || '').trim()}`,
      Accept: 'application/vnd.github+json',
      'User-Agent': 'buza-alarm-webhook',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  if (!r.ok) console.log('cron dispatch 실패', path, r.status, (await r.text()).slice(0, 300));
  return r.ok;
}

export default {
  async scheduled(event, env, ctx) {
    for (const p of due(new Date(event.scheduledTime))) {
      if (p.dash) {
        // 대시보드 레포 Actions 실행 — GH_TOKEN 에 stock-dashboard · Actions: Read and write 권한이 필요하다
        await gh(env, `${env.DASH_REPO || 'pcy604/stock-dashboard'}/actions/workflows/market-report.yml/dispatches`,
                 { ref: 'main', inputs: { kind: p.dash } });
      }
      if (p.bot) {
        await gh(env, `${env.GH_REPO}/dispatches`, { event_type: p.bot, client_payload: { [p.bot]: true } });
      }
    }
  },

  async fetch(request, env) {
    if (request.method !== 'POST') return new Response('ok');

    // 텔레그램이 보낸 요청이 맞는지 확인 — 아무나 이 URL을 두드려 Actions를 태우지 못하게
    const hdr = request.headers.get('X-Telegram-Bot-Api-Secret-Token');
    if (hdr !== env.WEBHOOK_SECRET) {
      // 진단용: 값 자체는 절대 찍지 않고 길이와 앞뒤 공백 여부만 남긴다.
      // 403이 났을 때 "글자가 다른가 / 공백이 붙었나 / URL 인코딩으로 잘렸나"를
      // 값 노출 없이 가르기 위한 것. 원인 확정되면 이 블록은 지운다.
      console.log('secret 불일치', JSON.stringify({
        헤더있음: hdr !== null,
        헤더길이: hdr ? hdr.length : 0,
        설정길이: env.WEBHOOK_SECRET ? env.WEBHOOK_SECRET.length : 0,
        헤더에공백: hdr ? hdr !== hdr.trim() : false,
        설정에공백: env.WEBHOOK_SECRET ? env.WEBHOOK_SECRET !== env.WEBHOOK_SECRET.trim() : false,
        공백제거후일치: hdr && env.WEBHOOK_SECRET
          ? hdr.trim() === env.WEBHOOK_SECRET.trim() : false,
      }));
      return new Response('forbidden', { status: 403 });
    }

    let update;
    try {
      update = await request.json();
    } catch {
      return new Response('bad json', { status: 400 });
    }

    const msg = update.message;
    const text = (msg && msg.text) || '';
    const chatId = msg && msg.chat && msg.chat.id;

    // 명령만 누르고 종목·링크가 없으면 → 사용법(답장 모드)만 보내고 끝. GitHub Actions 1분도 아낀다.
    const bare = text.trim().split('@')[0].toLowerCase();
    if (chatId && USAGE[bare]) {
      const ko = ((msg.from && msg.from.language_code) || 'ko').startsWith('ko');
      await tgSend(env, {
        chat_id: chatId,
        text: ko ? USAGE[bare][0] : (USAGE_EN[bare] || USAGE[bare][0]),
        reply_markup: { force_reply: true, input_field_placeholder: USAGE[bare][1] },
      });
      return new Response('usage');
    }

    // 사용법에 답장한 것(예: 'TSLA')이면 원래 명령으로 보고 접수 문구를 고른다(실제 변환은 bot.py).
    let effective = text;
    const rt = msg && msg.reply_to_message;
    if (rt && rt.from && rt.from.is_bot && text && !text.startsWith('/')) {
      const m = (rt.text || '').match(/(\/[a-z]+)\b/);
      if (m && USAGE[m[1]]) effective = `${m[1]} ${text}`;
    }

    // 즉시 접수 응답 — 실제 생성은 Actions에서 몇 분 걸리므로 먼저 반응부터
    if (chatId && effective.startsWith('/')) {
      const cmd = effective.split(/\s+/)[0].split('@')[0];
      const note = ACK[cmd];
      if (note) {
        await fetch(`https://api.telegram.org/bot${env.TELEGRAM_TOKEN}/sendMessage`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ chat_id: chatId, text: note }),
        });
      } else {
        // 접수 문구가 없는 짧은 명령도 GitHub 러너가 뜨는 데 15~20초가 걸린다. 그동안 아무 반응이
        // 없으면 '안 눌렸나' 싶어 다시 누른다 → 상단에 '입력 중…' 표시만 띄운다(2026-10-21).
        await fetch(`https://api.telegram.org/bot${env.TELEGRAM_TOKEN}/sendChatAction`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ chat_id: chatId, action: 'typing' }),
        }).catch(() => {});
      }
    }

    // GitHub Actions 즉시 트리거
    const gh = await fetch(`https://api.github.com/repos/${env.GH_REPO}/dispatches`, {
      method: 'POST',
      headers: {
        // ⚠️ trim() 필수. 시크릿을 붙여넣을 때 끝에 개행이나 공백이 한 칸만 섞여도
        //    Authorization 헤더가 깨져 GitHub 이 401 Bad credentials 를 돌려준다.
        //    토큰 자체는 멀쩡한데 값이 오염된 경우라, 화면만 보면 '만료됐나' 로 오진하게
        //    된다(2026-09-14 실측: 재발급·재입력을 반복해도 401 이 그대로였다).
        Authorization: `Bearer ${(env.GH_TOKEN || '').trim()}`,
        Accept: 'application/vnd.github+json',
        'User-Agent': 'buza-alarm-webhook',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        event_type: 'telegram',
        client_payload: { update },
      }),
    });

    // dispatch 결과를 응답 본문에 실어 보낸다. 텔레그램은 본문을 안 보므로
    // 동작에 영향이 없고, curl로 두드리면 GitHub이 뭐라 했는지 바로 읽힌다.
    // (wrangler tail이 연결 전에 끊기는 일이 잦아 로그만으로는 진단이 어려웠다)
    let detail = 'ok';
    if (!gh.ok) {
      const body = await gh.text();
      console.log('dispatch 실패', gh.status, body);
      // 값 자체는 절대 찍지 않고 모양만 남긴다 — 401 이 '토큰이 틀림' 인지
      // '값이 오염됨' 인지 이것만으로 갈린다. 정상 fine-grained PAT 은
      // 'github_pat_' 로 시작하고 길이가 90자 안팎이며 공백이 없다.
      const t = env.GH_TOKEN || '';
      console.log('토큰 모양', JSON.stringify({
        길이: t.length,
        접두어: t.slice(0, 11),
        앞뒤공백: t !== t.trim(),
        공백포함: /\s/.test(t.trim()),
      }));
      detail = `dispatch_failed ${gh.status} ${body.slice(0, 200)}`;

      // ⚠️ 예전엔 여기서 끝이었다. 사용자에게는 "준비 시작했어요" 만 가고 그 뒤로
      //    아무 말이 없다 — 봇이 죽은 건지 오래 걸리는 건지 알 수가 없다.
      //    실측(2026-09-10): /report BE·LMB 두 건이 ACK 만 받고 사라졌는데, 크론은
      //    정상이라 GitHub Actions 는 살아 있었다. 즉 이 dispatch 만 실패했는데
      //    그 사실이 어디에도 안 드러나 원인 추적에 며칠이 걸렸다.
      //    상태코드만 보면 바로 갈린다: 401=토큰 만료/오타, 403=권한 부족(PAT 에
      //    Contents:Read and write 필요), 404=GH_REPO 오타.
      if (chatId) {
        const hint = { 401: '토큰이 만료됐거나 틀렸어요',
                       403: '토큰 권한이 부족해요 (Contents: Read and write 필요)',
                       404: '레포 경로가 틀렸어요' }[gh.status] || '알 수 없는 오류';
        await fetch(`https://api.telegram.org/bot${env.TELEGRAM_TOKEN}/sendMessage`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chat_id: chatId,
            text: `⚠️ 실행 요청을 GitHub에 전달하지 못했어요 (HTTP ${gh.status} — ${hint}).\n`
                + `Cloudflare Worker의 GH_TOKEN을 확인해주세요. 명령은 처리되지 않았습니다.`,
          }),
        }).catch(() => {});
      }
    }
    // 텔레그램에는 항상 200을 줘야 재전송 루프에 빠지지 않음
    return new Response(detail);
  },
};
