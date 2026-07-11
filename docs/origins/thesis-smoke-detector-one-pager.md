# The Thesis Smoke Detector
### A one-page explainer

**In one line:** A monitoring system that watches your investment theses for early signs of breaking — and is deliberately built to make you act *less*, not more.

---

**The problem it solves.**
Two opposite failures sink long-term investors. The first is *inattention*: you hold a position for a reason (a "thesis"), the reason quietly stops being true, and you don't notice until the price has already told everyone else. The second is the mirror image — *over-attention*: you watch the market all day, react to every red candle and scary headline, and trade yourself to death on noise. Most tools (trading terminals, brokerage apps) are built for the second person and quietly make the problem worse.

The smoke detector lives in the gap between those two failures. You can't *predict* when a thesis breaks or a market cracks — complex systems genuinely don't work that way. But you *can* define, in advance, the specific conditions that would signal it, and have something tap you on the shoulder only when one of them actually trips. The point is to review the situation **deliberately, in calm** — instead of either missing it entirely or reacting to nothing.

**The core idea: a sensor suite, not an autopilot.**
The mental model is an aircraft cockpit. A stall warning isn't one instrument — it's the angle-of-attack probe *and* the airspeed indicator *and* the stick shaker, each watching something different, fused together, and escalating in intensity: a quiet dial you glance at, a louder alert that says "look now," and finally a physical shaker that's impossible to ignore. The detector works the same way. Most of its sensors are quiet dials. A few warrant a "go look." Almost none should ever be screaming — constant loudness is just noise, and noise is what retrains you into over-trading. And it is a *sensor*, never an autopilot: when something trips, it opens a **review**, it never places a trade. The navigator advises the heading; the pilot flies the plane.

**How it watches — layered sensor banks:**
- **Deterministic gauges** — clean numbers with hard thresholds, no AI involved: things like credit spreads, market volatility, or how far a holding has drifted from its intended size. Dumb, reliable, and incapable of making things up.
- **Agentic (AI) scouts** — for the signals that *can't* be reduced to a number (e.g., "is the regulatory or funding environment for this industry turning?"), AI agents go research the question. The key rule: they act as **research assistants, not judges**. Every claim has to come with a primary-source citation, and the agent reports what it *couldn't* verify. It assembles the evidence; the human makes the call.
- **Multiple independent scouts, triangulated** — the same question is sent to several agents, framed differently, and their answers are compared. Where they *agree* is high-confidence; where they *disagree* is exactly what gets a closer human look. Independent agents rarely invent the *same* falsehood, so agreement filters out hallucination, and disagreement points straight at what actually needs judgment.
- **A novelty layer** — a separate agent that watches the *other* sensors for drift: not "did a known thing happen," but "is the world starting to behave in a way none of these sensors were built for?" It's the closest you can get to a tripwire for the risk you didn't think to watch.

**The honest limit (this part is load-bearing).**
No sensor suite catches the risk nobody instrumented. A wall of green lights is exactly what a Thanksgiving turkey sees on day 1,000 — right up until the day it doesn't. So the detector is explicitly **not** the safety net; it's instrumentation bolted onto one. The real protection is structural: sensible position sizing, cash buffers, and never being a forced seller — the things that let you survive a shock you didn't see coming. The detector makes the *known* risks cheaper to watch; the *structure* survives the unknown ones. Letting a screen full of green talk you out of those buffers is the single trap it's designed to prevent, not create.

**Why it's a bit different.**
It's serious research infrastructure with the usual goals inverted. A quant's tools exist to find signals and trade fast. This one exists to surface *fewer*, better-verified signals on a deliberately *slow* schedule, for the specific purpose of keeping its owner **disciplined** — converting the constant urge to check into a system that mostly stays silent and only speaks when it matters. Its highest function is to let you stop watching.

---

*A personal discipline tool for thinking clearly about one's own holdings — not investment advice, and not a system that makes any trading decisions.*
