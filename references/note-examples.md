# Note examples

Synthetic notes. They are not a held-out video and not an eval-set talk. Each quote is a made-up spoken line, long enough to look like a real blockquote. `verify_note.py` checks R01–R17. R01–R16 are unchanged. R17 refuses a section whose prose does not share content words with that section's own quotes.

## Good — four sections, each claim on its own quote

The chair wobbles because one bolt is loose. The note keeps each claim on the line that states it.

```markdown
## 问题与做法

The wobble comes from a loose bolt, so tighten that bolt before you look for a new chair. Replacing the chair would skip the fault the speech actually names.

> The wobble comes from a loose bolt, so tighten that bolt before you buy another chair.

## 完整怎么做

Turn the bolt clockwise until the leg stops rocking, then sit once and check the same bolt. The speech gives that order and does not add another tool.

> Turn the bolt clockwise until the leg stops rocking, then sit once and check it.

## 翻车或别用

Stop if the bolt keeps spinning without catching, because the socket is stripped and tightening will not hold. Do not keep forcing a bolt that no longer bites.

> Stop if the bolt keeps spinning without catching, because the socket is stripped.

## 今天立刻动手一步

Tighten the loose bolt clockwise, then sit once and check that the rocking has stopped.

> Tighten the loose bolt clockwise, then sit once and check the rocking.
```

## Good — one section is 本节不适用

The speech teaches the tighten-and-sit sequence and never names a case to avoid. The limit section says so, and its quote is the line that shows the absence. The other claims stay on their own lines. The closer is not copied into every section.

```markdown
## 问题与做法

A rocking leg means the bolt is loose, and the fix starts at that bolt. Buying a different chair is not what this speech argues.

> A rocking leg means the bolt is loose, and the fix starts at that bolt.

## 完整怎么做

Turn the bolt clockwise, then sit once to test the leg. Do those two moves in that order.

> Turn the bolt clockwise, then sit once to test the leg.

## 翻车或别用

本节不适用：这段口播只讲了拧紧和试坐，没有说出不能用的情形。

> Turn the bolt clockwise, then sit once to test the leg after you finish.

## 今天立刻动手一步

Tighten the loose bolt, then sit once before you decide the chair is fine.

> Tighten the loose bolt, then sit once before you call the chair fine.
```

The third quote is a different stretch from the second, so the two sections do not reuse one blockquote.

## Bad — quote-section swap

The prose in 问题与做法 is about the loose bolt. The quote under it is the stripped-socket warning, which belongs under 翻车或别用. The warning's prose sits under the bolt quote. R17 fails both sections. Moving a verbatim quote to the wrong section is not a pass.

```markdown
## 问题与做法

The wobble comes from a loose bolt, so tighten that bolt before you buy another chair.

> Stop if the bolt keeps spinning without catching, because the socket is stripped.

## 翻车或别用

Stop if the bolt keeps spinning without catching, because the socket is stripped and will not hold.

> The wobble comes from a loose bolt, so tighten that bolt before you buy another chair.
```

## Bad — invented vehicle

The quote says to turn a bolt. The prose adds a checklist and a spreadsheet the speaker never named. That object is not in the section quote, so the claim is not allowed.

```markdown
## 完整怎么做

Open a spreadsheet and build a checklist with a row for every chair in the room, then assign an owner to each row.

> Turn the bolt clockwise until the leg stops rocking, then sit once and check it.
```

## Bad — thin stub / title as a watch

The title is treated as the viewing. There is no transcript quote, and the body does not say what was spoken.

```markdown
# How to stop a chair from wobbling

Fully understood. The title already says the chair wobbles and someone should fix it. No transcript was opened.
```
