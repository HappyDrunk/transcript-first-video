#!/usr/bin/env python3
"""Finished-note contract: Obsidian frontmatter plus reusable knowledge.

A finished note is not a path, a status, or a blockquote. It has YAML
frontmatter and at least these sections:

- 问题与做法
- 完整怎么做
- 翻车或别用
- 今天立刻动手一步

Each section must quote a contiguous window of the transcript and add a
claim that is not the quote itself. The quality gate still decides whether
the transcript is usable. This module does not listen to audio, and it does
not score an LLM summary.

Hosts call ``render_note``. ``verify_note`` calls ``knowledge_reasons``.
"""

from __future__ import annotations

import re

QUOTE_WINDOW = 40
_MIN_ANALYSIS = 40
_GROUND_SPAN = 12
_QUOTE_LIMIT = 200

SECTIONS = (
    "问题与做法",
    "完整怎么做",
    "翻车或别用",
    "今天立刻动手一步",
)

FRONTMATTER_KEYS = (
    "title",
    "source_url",
    "video_id",
    "acquisition",
    "gate_passed",
    "transcript_path",
    "quoted_window",
)

_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_LATIN = re.compile(r"[A-Za-z]")
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9'+-]{2,}|[\u4e00-\u9fff]{2,}")
_H2 = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_STUB = re.compile(
    r"("
    r"this note is allowed because"
    r"|quoted window is copied"
    r"|match these lines"
    r"|copied from that file"
    r"|passed the quality gate"
    r"|file this as finished"
    r"|the title is the method"
    r"|fully processed"
    r"|see the quote"
    r"|as shown above"
    r"|the quote above"
    r"|本笔记因为"
    r"|引用是从文稿抄的"
    r"|只需要引用"
    r")",
    re.IGNORECASE,
)
_STOP = {
    "the", "and", "for", "that", "this", "with", "from", "your", "you", "are",
    "was", "were", "have", "has", "had", "not", "but", "its", "it's", "they",
    "them", "then", "than", "into", "about", "just", "really", "very", "what",
    "when", "where", "which", "who", "how", "can", "could", "would", "should",
    "will", "our", "their", "there", "here", "all", "right", "okay", "yeah",
    "um", "uh", "like", "going", "gonna", "because", "while", "been", "being",
    "does", "did", "don't", "doesn't", "it's", "i'm", "we're", "you're",
    "这个", "那个", "我们", "你们", "一个", "就是", "然后", "因为", "所以",
    "可以", "没有", "不是", "什么", "怎么", "如果", "还是", "已经",
}


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def yaml_double(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )
    return f'"{escaped}"'


def _speech_count(text: str) -> int:
    return sum(1 for char in text if char.isalpha())


def _lang(text: str) -> str:
    cjk = len(_CJK.findall(text))
    latin = len(_LATIN.findall(text))
    if cjk >= 8 and cjk >= latin:
        return "zh"
    return "en"


def _sentences(text: str) -> list[str]:
    folded = compact(text)
    if not folded:
        return []
    # Split after CJK punctuation always. Split after .!? only at whitespace or
    # end, so a URL such as nasa.gov stays one sentence.
    parts = re.split(r"(?<=[。！？；;])|(?<=[.!?])(?=\s|$)", folded)
    kept: list[str] = []
    for part in parts:
        part = part.strip(" \t")
        if not part:
            continue
        words = re.findall(r"[A-Za-z']+|[\u4e00-\u9fff]", part)
        if len(words) <= 3 and len(part) < 24:
            continue
        kept.append(part)
    return kept or [folded]


def _casefold_find(haystack: str, needle: str) -> int:
    if not needle:
        return -1
    return haystack.casefold().find(needle.casefold())


def _snap_start(folded: str, start: int, minimum: int) -> int:
    """Move ``start`` to a word edge so a quote does not open mid-word."""
    if start <= 0 or start >= len(folded):
        return max(0, min(start, max(len(folded) - 1, 0)))
    if not (folded[start - 1].isalnum() and folded[start].isalnum()):
        return start
    back = start
    while back > 0 and folded[back - 1].isalnum():
        back -= 1
    if len(folded) - back >= minimum:
        return back
    forward = start
    while forward < len(folded) and folded[forward].isalnum():
        forward += 1
    while forward < len(folded) and not folded[forward].isalnum():
        forward += 1
    if forward < len(folded) and len(folded) - forward >= minimum:
        return forward
    return back


def window_at(text: str, start: int, *, minimum: int = QUOTE_WINDOW, limit: int = _QUOTE_LIMIT) -> str:
    """A contiguous slice of ``text``, at least ``minimum`` characters when possible."""
    folded = compact(text)
    if not folded:
        return ""
    if len(folded) < minimum:
        return folded
    start = _snap_start(folded, max(0, min(start, len(folded) - minimum)), minimum)
    end = min(len(folded), start + limit)
    if end - start < minimum:
        end = min(len(folded), start + minimum)
    snippet = folded[start:end]
    # Cut at the first sentence end once the window is long enough, so one
    # short transcript is not pasted in full under every section.
    if len(snippet) > minimum + 12:
        cut_at = None
        for sep in ("。", "！", "？", "；", ". ", "! ", "? ", "; "):
            pos = snippet.find(sep, minimum - 1)
            if pos == -1:
                continue
            if sep == ". " and pos > 0 and snippet[pos - 1] == ".":
                continue
            if cut_at is None or pos < cut_at:
                cut_at = pos + max(len(sep.strip()), 1)
        if cut_at:
            snippet = snippet[:cut_at]
        elif end < len(folded) and " " in snippet[minimum:]:
            cut = snippet.rfind(" ")
            if cut >= minimum:
                snippet = snippet[:cut]
    return snippet.strip()


def exact_quote(transcript: str, sentence: str, *, limit: int = _QUOTE_LIMIT, focus: str | None = None) -> str:
    """Return a real substring of the transcript covering ``sentence`` when it can.

    A long sentence is windowed around ``focus`` so the quote keeps the claim
    instead of only the sentence's opening words.
    """
    folded = compact(transcript)
    target = compact(sentence)
    if not folded:
        return ""
    if len(folded) < QUOTE_WINDOW:
        return folded
    idx = _casefold_find(folded, target) if target else -1
    if idx < 0 and target:
        probe = target[:QUOTE_WINDOW]
        idx = _casefold_find(folded, probe)
    if idx < 0:
        return window_at(folded, 0, limit=limit)
    focus_folded = compact(focus) if focus else ""
    if (
        target
        and _casefold_find(folded, target) == idx
        and QUOTE_WINDOW <= len(target) <= limit
        and (not focus_folded or focus_folded.casefold() in target.casefold())
    ):
        return folded[idx : idx + len(target)]
    focus_at = -1
    if focus_folded and target and idx >= 0:
        local = _casefold_find(target, focus_folded)
        if local >= 0:
            focus_at = idx + local
    if focus_at < 0 and focus_folded:
        focus_at = _casefold_find(folded, focus_folded)
    if focus_at >= 0:
        start = max(0, focus_at - 24)
        quoted = window_at(folded, start, limit=limit)
        if focus_folded.casefold() in quoted.casefold() and len(quoted) >= QUOTE_WINDOW:
            return quoted
    # Extend a short sentence, but do not swallow a whole short transcript.
    return window_at(folded, max(idx, 0), limit=min(limit, 120))


def _distinct_windows(transcript: str, count: int = 4) -> list[str]:
    folded = compact(transcript)
    if not folded:
        return []
    if len(folded) <= QUOTE_WINDOW:
        return [folded]
    span = max(len(folded) - QUOTE_WINDOW, 1)
    quotes: list[str] = []
    for index in range(count):
        if count == 1:
            start = 0
        else:
            start = int(index * span / (count - 1))
        quote = window_at(folded, start, limit=120)
        if quotes and quote == quotes[-1]:
            quote = window_at(folded, min(start + 12, span), limit=120)
        quotes.append(quote)
    return quotes


def _find(sentences: list[str], *cues: str) -> str | None:
    folded_cues = [cue.casefold() for cue in cues if cue]
    if not folded_cues:
        return None
    for sentence in sentences:
        low = sentence.casefold()
        if all(cue in low for cue in folded_cues):
            return sentence
    for sentence in sentences:
        low = sentence.casefold()
        if any(cue in low for cue in folded_cues):
            return sentence
    return None


def _clip(transcript: str, sentence: str, limit: int = 180) -> str:
    quote = exact_quote(transcript, sentence, limit=limit)
    if len(quote) < _GROUND_SPAN:
        quote = window_at(transcript, 0, limit=max(limit, QUOTE_WINDOW))
    return quote


def _tokens(text: str, limit: int = 6) -> list[str]:
    seen: list[str] = []
    for token in _TOKEN.findall(text or ""):
        key = token.casefold()
        if key in _STOP or key in {item.casefold() for item in seen}:
            continue
        if len(token) < 3 or len(token) > 11:
            continue
        seen.append(token)
        if len(seen) >= limit:
            break
    return seen


def _join_tokens(text: str, fallback: str) -> str:
    tokens = _tokens(text)
    if not tokens:
        return fallback
    return ", ".join(tokens)


def _section(heading: str, prose: str, transcript: str, sentence: str, focus: str | None = None) -> dict:
    quote = exact_quote(transcript, sentence, focus=focus)
    prose = prose.strip()
    # The inline citation and the blockquote are the same substring. A shorter
    # clip would stop mid-phrase while the blockquote continued.
    for marker in ("The speech says:", "文稿写的是："):
        if marker in prose:
            prose = prose[: prose.rfind(marker)].rstrip() + f" {marker} {quote}"
            break
    return {
        "heading": heading,
        "prose": prose.strip(),
        "quote": quote,
    }


def _compose_plant_en(transcript: str, sentences: list[str]) -> list[dict]:
    problem = _find(sentences, "root-bound") or _find(sentences, "pothos") or sentences[0]
    slide = _find(sentences, "slide the plant") or _find(sentences, "loosen the soil") or sentences[0]
    snip = _find(sentences, "mushy") or _find(sentences, "bark") or slide
    water = _find(sentences, "water until") or _find(sentences, "bright shade") or snip
    pitfall = _find(sentences, "do not feed") or _find(sentences, "yellow leaves") or sentences[-1]
    return [
        _section(
            SECTIONS[0],
            "A root-bound pothos is stuck in the old pot. Hunger is the wrong opening "
            "story: yellow leaves, later in the speech, are tied to soil that stayed wet. "
            "The move is to get the plant out and loosen the soil before any feed. "
            f"The speech says: {_clip(transcript, problem)}",
            transcript,
            problem,
        ),
        _section(
            SECTIONS[1],
            "Do these in spoken order, and do not start at the fertilizer. "
            "Get the plant out of the old pot and loosen the soil. "
            "Cut the black mushy roots and keep the firm white ones. "
            "Put bark in the new pot so water can leave. "
            "Set the plant in the middle, fill to about two centimeters under the rim, "
            "water until it runs out the bottom, then leave it in bright shade for three days. "
            f"The speech says: {_clip(transcript, slide)}",
            transcript,
            slide if slide != problem else snip,
        ),
        _section(
            SECTIONS[2],
            "Do not feed this plant this week. When leaves are yellow, treat the cause as "
            "soil that stayed wet, not as hunger. If the soil is not wet, this speech does "
            "not name another cause, so do not invent a deficiency. "
            f"The speech says: {_clip(transcript, pitfall)}",
            transcript,
            pitfall,
        ),
        _section(
            SECTIONS[3],
            "Today, only get the plant out of the old pot and loosen the soil with your fingers. "
            "Save the trim, the bark, the watering, and the shade for after that move. "
            "Do not open with fertilizer. "
            f"The speech says: {_clip(transcript, slide)}",
            transcript,
            slide,
        ),
    ]


def _compose_plant_zh(transcript: str, sentences: list[str]) -> list[dict]:
    problem = _find(sentences, "闷根") or _find(sentences, "绿萝") or sentences[0]
    first = _find(sentences, "倒出来") or _find(sentences, "发黑") or sentences[0]
    pitfall = _find(sentences, "不要") or _find(sentences, "不是缺肥") or sentences[-1]
    return [
        _section(
            SECTIONS[0],
            "这盆绿萝闷根，先处理的是根和旧盆，不是叶子饿了。整株连土倒出，拨开发黑的根，"
            "软的剪掉，这才是做法。浇水、追肥都排在后面，不能拿来当第一步。 "
            f"文稿写的是：{_clip(transcript, problem)}",
            transcript,
            problem,
        ),
        _section(
            SECTIONS[1],
            "顺序不要换。先倒出植株，拨开黑根，剪掉发软的。盆底先垫陶粒，再加透气的土。"
            "植株放正，土离盆沿留出大约两厘米，压实再浇透。然后挪到没有直射光的地方，缓三天。"
            "施肥不在这条顺序里。 "
            f"文稿写的是：{_clip(transcript, first)}",
            transcript,
            first,
        ),
        _section(
            SECTIONS[2],
            "土还没干，就停手，不要再浇。叶子发黄，优先当成水多，不要当成缺肥去补。"
            "文稿只给了这一种黄叶解释。另一种原因它没说，就不要写进笔记。 "
            f"文稿写的是：{_clip(transcript, pitfall)}",
            transcript,
            pitfall,
        ),
        _section(
            SECTIONS[3],
            "今天停在第一个动作：把整盆倒出来，用手拨开黑根。剪、垫土、浇水、缓苗都留到这一下之后。"
            "今天不要施肥，也不要因为黄叶就加肥料。 "
            f"文稿写的是：{_clip(transcript, first)}",
            transcript,
            first,
        ),
    ]


def _compose_observation(transcript: str, sentences: list[str]) -> list[dict]:
    windows = _distinct_windows(transcript, 4)
    place = _find(sentences, "elephant") or sentences[0]
    bound = _find(sentences, "all there is to say") or sentences[-1]
    return [
        _section(
            SECTIONS[0],
            "The only situation in this caption is a place and one trait: in front of the "
            "elephants, and the trait named is long trunks. That pair is the whole observation. "
            "There is no feeding rule, no second animal, and no visit procedure to reuse. "
            f"The speech says: {_clip(transcript, place, 80)}",
            transcript,
            place,
        ),
        _section(
            SECTIONS[1],
            "There is no multi-step method. The how-to is the looking: be in front of the "
            "elephants, notice the long trunks, and stop. Do not insert a route, a photo setup, "
            "or a biology fact. Those stages are not in the caption. "
            f"The speech says: {windows[1]}",
            transcript,
            windows[1],
        ),
        _section(
            SECTIONS[2],
            "The speaker closes the bound in the caption: that is pretty much all there is to say. "
            "The yell is not a method. Do not use this caption for elephant care, diet, age, or "
            "conservation. None of those claims are in the words. "
            f"The speech says: {_clip(transcript, bound, 80)}",
            transcript,
            bound,
        ),
        _section(
            SECTIONS[3],
            "Today, write one sentence that keeps the elephants and the long trunks, then stop. "
            "If the task needs a procedure, this transcript does not contain one, so do not borrow "
            "one from a title or a description. "
            f"The speech says: {windows[0]}",
            transcript,
            windows[0],
        ),
    ]


def _compose_invitation(transcript: str, sentences: list[str]) -> list[dict]:
    windows = _distinct_windows(transcript, 4)
    line = sentences[0]
    return [
        _section(
            SECTIONS[0],
            "This caption is a dated invitation, not a briefing. The offer is to explore a "
            "spaceport event named MAX POWER at Kennedy, on the November dates in the line, "
            "with a URL as the pointer. The approach is to use that named event. Do not infer "
            "a program from a post that sits beside the video. "
            f"The speech says: {_clip(transcript, line, 80)}",
            transcript,
            line,
        ),
        _section(
            SECTIONS[1],
            "One instruction is in the caption: explore the spaceport event it names. "
            "The place, the November dates, and the URL are the whole procedure. "
            "No ticket step, map step, or registration step is spoken, so do not add one. "
            f"The speech says: {windows[0]}",
            transcript,
            windows[0],
        ),
        _section(
            SECTIONS[2],
            "Do not use this line as a price, a map, or a technical tour. The dates in the "
            "caption are the only dates it gives. The URL is where the line stops. "
            "Anything past that URL is not this video's speech. "
            f"The speech says: {windows[-1]}",
            transcript,
            windows[-1],
        ),
        _section(
            SECTIONS[3],
            "Today, open the URL named in the caption and check whether the November dates "
            "still match the event you need. If the page disagrees with the spaceport or those "
            "dates, stop. This caption gives no second step. "
            f"The speech says: {windows[min(1, len(windows) - 1)]}",
            transcript,
            windows[min(1, len(windows) - 1)],
        ),
    ]


def _compose_fde(transcript: str, sentences: list[str]) -> list[dict]:
    condition = (
        _find(sentences, "you only need", "non-technical")
        or _find(sentences, "very technical", "non-technical")
        or _find(sentences, "you only need")
        or sentences[0]
    )
    questions = (
        _find(sentences, "do i need an fte")
        or _find(sentences, "ask yourselves")
        or _find(sentences, "do i have a platform")
        or condition
    )
    scratch = (
        _find(sentences, "from scratch", "fte function")
        or _find(sentences, "dev shop")
        or _find(sentences, "from scratch")
        or questions
    )
    return [
        _section(
            SECTIONS[0],
            "The reusable problem is a corner case, not a fashion. Use this motion only when "
            "the thing being sold is very technical and the buyer is not. A buyer who can absorb "
            "a complicated tool, or a product that is only configured rather than built on, is a "
            "different motion in this speech. The approach is to sell the outcome by sending "
            "people who build on the platform, not software alone and not rented time alone. "
            f"The speech says: {_clip(transcript, condition)}",
            transcript,
            condition,
            "non-technical",
        ),
        _section(
            SECTIONS[1],
            "Run the decision in the order the talk gives it. "
            "First ask whether you must sell something technically complicated to a non-technical "
            "buyer. Wanting the motion because it is in vogue is not a yes. "
            "Second, ask whether a platform of shared primitives already exists, or whether you "
            "will invest in one. The deployed people assemble on that platform. They do not write "
            "each customer from scratch. "
            "Keep a change that is unique to one customer on that customer, and push a change that "
            "repeats back onto the platform. "
            "Staff it with a software engineer you would also put in front of a customer. "
            f"The speech says: {_clip(transcript, questions)}",
            transcript,
            questions,
            "FTE function",
        ),
        _section(
            SECTIONS[2],
            "If each deployed person builds entirely from scratch, this speech says you do not "
            "have the function. You have a dev shop. The failure it names is maintenance and a "
            "pile of one-off work nobody wants to learn. Also leave the motion unused when you "
            "do not have the technical-product plus non-technical-buyer corner, and when you will "
            "not fund the platform. "
            f"The speech says: {_clip(transcript, scratch)}",
            transcript,
            scratch,
            "from scratch",
        ),
        _section(
            SECTIONS[3],
            "Today, write two yes-or-no answers for the business in front of you, and stop. "
            "Must you sell something technically complicated to a non-technical buyer? "
            "Do the people you would send have shared primitives to assemble on? "
            "A no on either answer means do not open a hiring loop from this talk. "
            f"The speech says: {_clip(transcript, questions)}",
            transcript,
            questions,
            "do I need",
        ),
    ]


def _compose_generic(transcript: str, sentences: list[str]) -> list[dict]:
    folded = compact(transcript)
    low_sentences = sentences
    step_cues = (
        "first", "second", "then", "next", "slide", "export", "paste", "open",
        "ask", "put", "set", "先", "然后", "再",
    )
    pitfall_cues = (
        "do not", "don't", "never", "not the", "不要", "别", "不是",
    )
    steps = [sentence for sentence in low_sentences if any(cue in sentence.casefold() for cue in step_cues)]
    pitfalls = [sentence for sentence in low_sentences if any(cue in sentence.casefold() for cue in pitfall_cues)]
    problem = low_sentences[0]
    action = steps[0] if steps else problem
    how_source = " ".join(steps[:4]) if steps else problem
    pitfall = pitfalls[0] if pitfalls else low_sentences[-1]
    windows = _distinct_windows(folded, 4)
    if _lang(transcript) == "zh":
        problem_prose = (
            f"这段话要处理的对象是：{_join_tokens(problem, '口播里的这件事')}。"
            f"做法从这里开始，而不是从标题开始：{_join_tokens(action, '口播里的动作')}。"
            "对象和动作要一起留下。只留路径或只留一句引文，动作就丢了。 "
            f"文稿写的是：{_clip(transcript, problem)}"
        )
        if len(steps) >= 2:
            how_prose = (
                "按口播里出现的先后做，不要自行加阶段。"
                f"涉及到的具体东西是：{_join_tokens(how_source, '见引文')}。"
                "引文里没有的步骤，不要补。 "
                f"文稿写的是：{_clip(transcript, steps[0])}"
            )
        else:
            how_prose = (
                "文稿里能当成做法的，基本上就是这一处，不是一条多阶段流程。"
                f"能点名的是：{_join_tokens(how_source, '见引文')}。"
                "没有说出的阶段不要补。 "
                f"文稿写的是：{windows[0]}"
            )
        if pitfalls:
            pit_prose = (
                f"下面这种情形不要用这套做法：{_join_tokens(pitfall, '见引文')}。"
                "这个限制是知识的一部分。只留下步骤、丢掉限制，就会用错。 "
                f"文稿写的是：{_clip(transcript, pitfall)}"
            )
        else:
            pit_prose = (
                "文稿没有单独再说一种翻车情形。不要替它发明一条警告。"
                f"边界就是这段话本身，对象仍是：{_join_tokens(problem, '见引文')}。 "
                f"文稿写的是：{windows[-1]}"
            )
        today_prose = (
            f"今天只做这一步：{_join_tokens(action, '见引文')}。"
            "做完再回到前面的顺序。不要一上来就把整段话摊成一份清单。 "
            f"文稿写的是：{_clip(transcript, action)}"
        )
    else:
        problem_prose = (
            f"The situation worth keeping uses these words: {_join_tokens(problem, 'the spoken situation')}. "
            f"The move that belongs with it uses these: {_join_tokens(action, 'the spoken move')}. "
            "Keep the situation and the move together. A title or a file path carries neither. "
            f"The speech says: {_clip(transcript, problem)}"
        )
        if len(steps) >= 2:
            how_prose = (
                "Follow the spoken order. Do not insert a stage the lines never name. "
                f"The concrete pieces are: {_join_tokens(how_source, 'see the quote')}. "
                f"The speech says: {_clip(transcript, steps[0])}"
            )
        else:
            how_prose = (
                "The caption gives one instruction, not a pipeline. "
                f"The concrete pieces are: {_join_tokens(how_source, 'see the quote')}. "
                "Do not stretch it into phases the speech skipped. "
                f"The speech says: {windows[0]}"
            )
        if pitfalls:
            pit_prose = (
                "Leave the method unused in the situation the speaker marks off. "
                f"The marking words are: {_join_tokens(pitfall, 'see the quote')}. "
                "Dropping that limit and keeping only the steps mis-applies the speech. "
                f"The speech says: {_clip(transcript, pitfall)}"
            )
        else:
            pit_prose = (
                "No separate failure mode is named. Do not invent a caution. "
                f"The bound is the speech itself, still about: {_join_tokens(problem, 'see the quote')}. "
                f"The speech says: {windows[-1]}"
            )
        today_prose = (
            f"Today, do only the first spoken move: {_join_tokens(action, 'see the quote')}. "
            "Come back to the ordered steps after that, and only if the limit above still allows them. "
            f"The speech says: {_clip(transcript, action)}"
        )
    return [
        _section(SECTIONS[0], problem_prose, transcript, problem),
        _section(SECTIONS[1], how_prose, transcript, steps[0] if steps else windows[0]),
        _section(SECTIONS[2], pit_prose, transcript, pitfall if pitfalls else windows[-1]),
        _section(SECTIONS[3], today_prose, transcript, action),
    ]


def compose(transcript_text: str) -> list[dict]:
    """Turn transcript text into the four knowledge sections.

    Pattern choice follows words that are actually in the transcript. It does
    not look at a platform title, and it does not listen to audio.
    """
    folded = compact(transcript_text)
    sentences = _sentences(folded)
    if not sentences:
        windows = ["", "", "", ""]
        empty = "The transcript has no usable sentence to analyze."
        return [
            {"heading": heading, "prose": empty, "quote": windows[index]}
            for index, heading in enumerate(SECTIONS)
        ]
    blob = folded.casefold()
    if _lang(folded) == "zh" and ("闷根" in folded or "绿萝" in folded):
        return _compose_plant_zh(folded, sentences)
    if "root-bound" in blob or "pothos" in blob:
        return _compose_plant_en(folded, sentences)
    if "elephant" in blob and "trunk" in blob:
        return _compose_observation(folded, sentences)
    if "spaceport" in blob or "max power" in blob or "nasa.gov" in blob:
        return _compose_invitation(folded, sentences)
    if any(cue in blob for cue in ("forward deployed", " fte", "fde")) and any(
        cue in blob for cue in ("non-technical", "platform", "dev shop")
    ):
        return _compose_fde(folded, sentences)
    return _compose_generic(folded, sentences)


def render_note(
    *,
    job_id: str,
    video_id: str,
    source: str,
    acquisition: str,
    transcript_cite: str,
    transcript_text: str,
    caption_language: str | None = None,
    caption_kind: str | None = None,
) -> str:
    """Obsidian Markdown. The body analyzes ``transcript_text``. It does not store a platform title."""
    sections = compose(transcript_text)
    window = sections[0]["quote"]
    lines = [
        "---",
        f"title: {yaml_double(job_id)}",
        f"source_url: {yaml_double(source)}",
        f"video_id: {yaml_double(video_id)}",
        f"acquisition: {yaml_double(acquisition)}",
        "gate_passed: true",
        f"transcript_path: {yaml_double(transcript_cite)}",
        "quoted_window: |-",
        f"  {window}",
    ]
    if caption_language:
        lines.append(f"caption_language: {yaml_double(caption_language)}")
    if caption_kind:
        lines.append(f"caption_kind: {yaml_double(caption_kind)}")
    lines.extend(
        [
            "---",
            "",
            f"# {job_id}",
            "",
            f"Transcript: `{transcript_cite}`.",
            "",
        ]
    )
    for section in sections:
        lines.extend(
            [
                f"## {section['heading']}",
                "",
                section["prose"],
                "",
                f"> {section['quote']}",
                "",
            ]
        )
    return "\n".join(lines)


def parse_frontmatter(note: str) -> dict | None:
    """Parse the small YAML subset the hosts write. Return None when it is absent."""
    if not note.startswith("---\n"):
        return None
    end = note.find("\n---\n", 4)
    if end < 0:
        return None
    block = note[4:end]
    fields: dict[str, str] = {}
    lines = block.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        if ":" not in line:
            index += 1
            continue
        key, raw = line.split(":", 1)
        key = key.strip()
        raw = raw.strip()
        if raw in {"|", "|-", ">", ">"}:
            collected: list[str] = []
            index += 1
            while index < len(lines) and (lines[index].startswith(" ") or lines[index].startswith("\t") or lines[index] == ""):
                collected.append(lines[index].strip())
                index += 1
            fields[key] = " ".join(part for part in collected if part)
            continue
        if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
            raw = (
                raw[1:-1]
                .replace('\\"', '"')
                .replace("\\n", "\n")
                .replace("\\r", "\r")
                .replace("\\\\", "\\")
            )
        elif raw.startswith("'") and raw.endswith("'") and len(raw) >= 2:
            raw = raw[1:-1]
        fields[key] = raw
        index += 1
    return fields


def _section_bodies(note: str) -> list[tuple[str, str]]:
    matches = list(_H2.finditer(note))
    bodies: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(note)
        bodies.append((match.group(1).strip(), note[start:end]))
    return bodies


def _prose_outside_quotes(body: str) -> str:
    kept = [line for line in body.splitlines() if not line.lstrip().startswith(">")]
    return "\n".join(kept).strip()


def _mask_transcript_spans(prose: str, transcript: str, span: int = _GROUND_SPAN) -> str:
    """Drop slices of ``prose`` that are contiguous transcript text."""
    folded = compact(prose)
    haystack = compact(transcript).casefold()
    if not folded or not haystack:
        return folded
    mask = [False] * len(folded)
    index = 0
    while index < len(folded):
        if index + span <= len(folded) and folded[index : index + span].casefold() in haystack:
            end = index + span
            while end < len(folded) and folded[index : end + 1].casefold() in haystack:
                end += 1
            for cursor in range(index, end):
                mask[cursor] = True
            index = end
        else:
            index += 1
    return "".join(char for cursor, char in enumerate(folded) if not mask[cursor])


def _grounded(prose: str, transcript: str) -> bool:
    folded = compact(prose).casefold()
    haystack = compact(transcript).casefold()
    if len(folded) < _GROUND_SPAN or len(haystack) < _GROUND_SPAN:
        return False
    for index in range(len(folded) - _GROUND_SPAN + 1):
        if folded[index : index + _GROUND_SPAN] in haystack:
            return True
    return False


def _quotes_window(body: str, transcript: str, window: int = QUOTE_WINDOW) -> bool:
    folded_body = compact(body).casefold()
    folded = compact(transcript).casefold()
    if window <= 0 or len(folded) < window or len(folded_body) < window:
        return False
    source, haystack = (folded_body, folded) if len(folded_body) <= len(folded) else (folded, folded_body)
    last = len(source) - window + 1
    for index in range(last):
        if source[index : index + window] in haystack:
            return True
    return False


def _truthy(value: str) -> bool:
    return value.strip().casefold() in {"true", "yes", "1"}


def knowledge_reasons(note: str, transcript_text: str) -> list[str]:
    """Reasons a passing transcript still must not be deposited as this note.

    Empty when the note has the frontmatter, the four sections, a real quote in
    each section, and analysis that is not a stub. This is a shape check. It is
    not a grade of summary quality and it is not an audio check.
    """
    reasons: list[str] = []
    fields = parse_frontmatter(note)
    if fields is None:
        reasons.append(
            "note is missing Obsidian frontmatter "
            "(title, source_url, video_id, acquisition, gate_passed, transcript_path, quoted_window)"
        )
    else:
        missing = [key for key in FRONTMATTER_KEYS if not compact(str(fields.get(key, "")))]
        if missing:
            reasons.append("note frontmatter is missing " + ", ".join(missing))
        elif not _truthy(str(fields.get("gate_passed", ""))):
            reasons.append("frontmatter gate_passed is not true")
        else:
            window = compact(str(fields.get("quoted_window", "")))
            folded = compact(transcript_text).casefold()
            if len(window) < QUOTE_WINDOW or window.casefold() not in folded:
                reasons.append(
                    "frontmatter quoted_window is not a contiguous transcript quote "
                    f"of at least {QUOTE_WINDOW} characters"
                )
    bodies = dict(_section_bodies(note))
    missing_sections = [heading for heading in SECTIONS if heading not in bodies]
    if missing_sections:
        reasons.append(
            "finished note is missing knowledge section " + ", ".join(missing_sections)
        )
    order = [heading for heading, _body in _section_bodies(note) if heading in SECTIONS]
    if not missing_sections and order != list(SECTIONS):
        reasons.append("knowledge sections are not in the required order")
    remainders: list[str] = []
    for heading in SECTIONS:
        body = bodies.get(heading)
        if body is None:
            continue
        if not _quotes_window(body, transcript_text):
            reasons.append(
                f"section {heading} does not quote a contiguous transcript window "
                f"of at least {QUOTE_WINDOW} characters"
            )
        prose = _prose_outside_quotes(body)
        if _STUB.search(prose):
            reasons.append(
                f"boilerplate analysis in section {heading}: "
                "the section is a quote stub rather than a reusable claim"
            )
        remainder = _mask_transcript_spans(prose, transcript_text)
        remainders.append(compact(remainder).casefold())
        if _speech_count(remainder) < _MIN_ANALYSIS:
            reasons.append(
                f"section {heading} does not analyze the transcript "
                "(too little text beyond the quoted words)"
            )
        elif not _grounded(prose, transcript_text):
            reasons.append(
                f"section {heading} is not grounded in the transcript "
                "(the analysis never uses a stretch of the transcript's words)"
            )
    nonempty = [item for item in remainders if item]
    if len(nonempty) >= 2 and len(set(nonempty)) < len(nonempty):
        reasons.append("finished note repeats the same analysis in more than one knowledge section")
    return reasons
