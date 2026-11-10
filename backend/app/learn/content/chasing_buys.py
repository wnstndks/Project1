"""Lesson `chasing-buys`: buying right after a run-up (skill `chasing`)."""

from app.learn.model import Lesson, Question, Reference, Section

LOC_FOR_SEC = "Library of Congress Federal Research Division, for the U.S. SEC"

LESSON = Lesson(
    id="chasing-buys",
    title_ko="추격 매수: 급등 뒤에 사는 습관",
    level="basic",
    skill_codes=("chasing",),
    watch_kinds=(),
    summary_ko=(
        "최근 한 달 사이 크게 오른 것을 보고 그 상승 자체를 이유로 사는 "
        "행동이 왜 반복되는지, 사고 싶은 마음과 주문 사이에 무엇을 두는지 "
        "봅니다. 코치 페이지는 그런 매수를 내 거래 기록에서 찾아 보여 줍니다."
    ),
    sections=(
        Section(
            heading_ko="급등 뒤 매수란 무엇이고 왜 자주 나오나",
            kind="fact",
            paragraphs=(
                "이 강의에서 '급등 뒤 매수'는 최근 한 달 사이 가격이 크게 오른 "
                "것을 본 뒤, 그 상승 자체를 이유로 사는 것을 말합니다. 크게 오른 "
                "종목은 뉴스와 대화방에 자주 등장해 눈에 잘 띕니다. 많은 사람이 "
                "가는 방향을 따라가는 군중 행동을, 미국 증권거래위원회 의뢰로 미 "
                "의회도서관이 정리한 투자자 행동 보고서는 '열광과 공황'이라는 "
                "이름의 흔한 행동 유형으로 적습니다[1].",
                "지난 몇 주의 상승이 이어질 것이라는 가정만으로 들어가는 매수는, "
                "어디서 틀렸다고 보고 나올지 정하지 않은 채 시작된다는 점에서 "
                "들어가는 조건·나오는 가격·금액을 미리 정해 둔 추세 따라가기 "
                "매매와 다릅니다. 미국 증권거래위원회의 투자자 경고문은 화제가 된 "
                "종목을 그 가정만으로 단기 매매할 때의 손실 가능성을 짚습니다[2]. "
                "과거 수익률에 과하게 주목하는 경향 역시 같은 보고서가 꼽는 흔한 "
                "유형입니다[1].",
                "놓칠까 봐 쫓아가는 마음(흔히 FOMO라고 부릅니다)은 한국 개인 "
                "투자자 교육 자료에서도 대표적인 함정으로 다룹니다[3]. 이런 "
                "마음의 쏠림(편향)은 여러 연구에서 반복해서 관찰된 것이지, "
                "특정한 사람의 결함이 아닙니다[4].",
            ),
            callout_ko=(
                "급등 뒤에 샀다고 해서 결과가 늘 나쁜 것은 아니고, 상승이 더 "
                "이어지는 경우도 있습니다. 이 강의가 보는 것은 결과가 아니라, "
                "상승 하나만 보고 들어간 과정입니다."
            ),
        ),
        Section(
            heading_ko="사고 싶은 마음과 주문 사이에 끼우는 한 단계",
            kind="principle",
            paragraphs=(
                "사고 싶은 마음과 주문 사이에 '미리 정해 둔 것'을 하나 끼워 넣는 "
                "방법이 흔히 쓰입니다. 어느 것도 수익을 보장하지 않지만, '왜 지금 "
                "사는지'를 스스로 설명하게 만듭니다.",
            ),
            bullets=(
                "매수 조건을 미리 적어 둡니다. '얼마면 산다' 한 줄이 아니라 "
                "'실적 발표를 확인한 뒤', '목표 비중보다 낮아지면'처럼 어떤 "
                "상태가 되면 사는지를 글로 남기고, 조건 밖의 매수는 '예외'라고 "
                "따로 적어 둡니다.",
                "주문 전에 '여기까지 내려가면 내 근거가 깨진다'는 가격과 그때의 "
                "손실액을 먼저 적습니다. 급등 뒤에는 그 가격이 멀어서 손실액이 "
                "커지는 경우가 많습니다.",
                "나눠 삽니다. 첫 매수가 작으면 상승이 꺾였을 때 걸려 있는 금액이 "
                "작습니다. 다만 다음 매수도 미리 적은 조건이 맞을 때만 하고, "
                "시간이 지났다고 보태는 것은 나눠 사기가 아닙니다.",
                "주문 전에 하루를 둡니다. 하루치 움직임을 놓칠 수는 있지만, 다음 "
                "날에도 같은 조건이 남아 있는지 확인하는 값으로 치는 방법입니다.",
            ),
            callout_ko="넷 가운데 하나만 골라 다음 매수에 써 보는 것으로 충분합니다.",
        ),
        Section(
            heading_ko="이 앱에서는",
            kind="app",
            route="/coach",
            paragraphs=(
                "코치 페이지의 습관 점검은 매수 전 20봉(주식은 약 한 달) 동안 "
                "종가가 15% 넘게 오른 뒤 산 거래를 최근 1년 기록에서 찾아 목록과 "
                "건수를 보여 주고, 봉이 모자라 세지 못한 매수는 따로 건수로 알려 "
                "줍니다. 기준은 주식과 코인이 같아, 20봉이 20일이고 그 사이 "
                "15%가 드물지 않은 코인 매수가 더 자주 집계됩니다.",
                "공부 페이지의 '내 기록으로 본 습관'은 그 건수를 봉이 있는 매수 "
                "수로 나눈 비율을 적고, 30% 이상이면 '뚜렷함', 15% 이상이면 '조금 "
                "보임', 그 아래면 '걸린 것 없음', 봉이 있는 매수가 5건이 안 되면 "
                "'기록 부족'입니다. 어느 쪽도 그 매수가 잘못됐다는 뜻은 아니며, "
                "앱은 매수 이유나 메모를 보지 않고 가격 상승폭만 봅니다. 가져오기 "
                "페이지로 넣은 거래는 거래일이 가져온 날이라, 거래 페이지에서 실제 "
                "날짜로 고치기 전에는 이 집계가 실제와 다릅니다.",
                "들고 있는 종목은 규칙 페이지가 손절 발동가와 그때의 손실액을 "
                "계산해 주지만, 처음 사는 종목은 주문 전에 직접 어림해야 "
                "합니다(크기 강의의 계산 예). 거래 입력 때 메모 칸에 이유를 "
                "남기면, 나중에 집계된 거래의 이유를 다시 읽어 볼 수 있습니다.",
            ),
        ),
    ),
    general_example_ko=(
        "AAA가 약 한 달(20봉) 동안 20% 오른 것을 보고 다음 날 100만원어치를 "
        "샀다면, 매수 전 20봉의 상승폭이 15%를 넘어 '급등 뒤 매수'로 "
        "집계됩니다. BBB를 메모 칸에 적어 둔 조건대로 50만원씩 두 번 샀더라도 "
        "직전 20봉 상승이 기준을 넘었다면 똑같이 집계됩니다. 그때 차이를 보여 "
        "주는 것은 앱이 아니라 내가 남긴 메모입니다."
    ),
    references=(
        Reference(
            title="Behavioral Patterns and Pitfalls of U.S. Investors",
            url="https://www.sec.gov/investor/locinvestorbehaviorreport.pdf",
            publisher=LOC_FOR_SEC,
            lang="en",
            note_ko=(
                "2010년 8월 보고서(PDF). 잦은 매매, 처분 효과, 과거 수익률에 "
                "대한 과도한 주목, 열광과 공황(군중 행동) 등 개인 투자자에게서 "
                "흔히 관찰되는 행동 유형을 연구 문헌과 함께 정리했습니다. 영어 "
                "자료입니다."
            ),
            accessed="2026-11",
        ),
        Reference(
            title=(
                "Investor Alert: Thinking About Investing in the Latest Hot Stock? "
                "Understand the Significant Risks of Short-Term Trading Based on Social Media"
            ),
            url=(
                "https://www.investor.gov/introduction-investing/general-resources/news-alerts"
                "/alerts-bulletins/investor-alerts/investor-alert-thinking-about-investing"
                "-latest-hot-stock-understand-significant-risks-short-term"
            ),
            publisher="U.S. SEC Investor.gov",
            lang="en",
            note_ko=(
                "소셜 미디어에서 화제가 된 종목을 상승이 이어진다는 가정만으로 "
                "단기 매매할 때의 손실 가능성을 짚는 경고문입니다. 이 강의는 그 "
                "범위에서만 인용합니다. 영어 자료입니다."
            ),
            accessed="2026-11",
        ),
        Reference(
            title="주식과 결혼하기 전, 연애부터 시작하자",
            url="https://www.kcie.or.kr/mobile/guide/24/31/web_view?series_idx=&content_idx=1223",
            publisher="전국투자자교육협의회",
            lang="ko",
            note_ko=(
                "개인 투자자가 빠지기 쉬운 FOMO(놓칠까 봐 쫓아가는 마음)와 확증 "
                "편향을 다룬 투자자 교육 글입니다."
            ),
            accessed="2026-11",
        ),
        Reference(
            title="Annotated Bibliography on the Behavioral Characteristics of U.S. Investors",
            url="https://www.sec.gov/investor/locinvestorbehaviorbib.pdf",
            publisher=LOC_FOR_SEC,
            lang="en",
            note_ko=(
                "위 보고서와 함께 만들어진 개인 투자자 행동 연구 목록(PDF, "
                "2010년). 군중 행동과 과거 성과 쫓기에 관한 연구가 포함됩니다. "
                "영어 자료입니다."
            ),
            accessed="2026-11",
        ),
    ),
    quiz=(
        Question(
            prompt_ko="급등 뒤 매수가 자주 반복되는 배경으로 이 강의가 든 것은?",
            choices=(
                "손실을 확정하기 싫어 못 파는 마음(처분 효과)",
                "많은 사람이 가는 방향을 따라가는 군중 행동과, 최근 상승이 이어질 것이라는 가정",
                "회사 실적을 너무 오래 분석하다 매수 시점을 놓치는 습관",
            ),
            answer=1,
            why_ko=(
                "처분 효과는 같은 보고서에 나오지만 '파는 쪽'의 행동이라 이 "
                "강의의 주제가 아닙니다. 급등 뒤 매수는 군중 행동과 '상승이 "
                "이어질 것'이라는 가정에서 자주 나옵니다. 분석이 길어 시점을 "
                "놓치는 것은 급등 뒤 매수와 반대 방향의 문제입니다."
            ),
        ),
        Question(
            prompt_ko="급등 뒤에 산 거래는 항상 손해로 끝난다?",
            choices=(
                "아니다. 결과만으로는 알 수 없다",
                "그렇다. 급등 뒤에 샀다는 것 자체가 손실의 원인이라 상승폭이 클수록 손해도 크다",
                "상승폭이 15%를 넘었을 때만 손해로 끝난다",
            ),
            answer=0,
            why_ko=(
                "급등이 더 이어져 이익으로 끝나는 경우도 있습니다. 15%는 앱이 "
                "'급등 뒤 매수'를 세는 기준일 뿐 손익과는 관계가 없습니다."
            ),
        ),
        Question(
            prompt_ko="이 앱의 코치 페이지가 '급등 뒤 매수'로 세는 거래는?",
            choices=(
                "매수 전 20봉 동안 종가가 15% 넘게 오른 뒤 산 거래",
                "매수 다음 날 가격이 하락한 거래",
                "매수 전 20봉 동안 종가가 15% 넘게 내린 뒤 산 거래",
                "메모 없이 입력한 거래",
            ),
            answer=0,
            why_ko=(
                "기준은 매수 뒤의 결과가 아니라 매수 전 20봉의 상승폭이고, 내린 "
                "뒤 산 거래는 세지 않습니다. 메모 유무는 집계에 영향이 없고 "
                "'메모 없는 거래' 항목에서 따로 봅니다."
            ),
        ),
    ),
    takeaway_ko="급등을 보고 사고 싶을 때는 하루 뒤, 나올 가격과 이유를 메모 칸에 적고 주문한다.",
)
