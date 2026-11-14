"""Prompt text (SPEC 11.3). Bump PROMPT_VERSION on any change; it is part of every cache key."""

PROMPT_VERSION = "v1"

CLASSIFY_SYSTEM = (
    "You compare two versions of one section of a US drug label. You are given one added or "
    "changed unit of text. Decide whether it is a substantive safety change (a new or stronger "
    "warning, adverse reaction, contraindication, interaction or population restriction) or "
    "editorial (formatting, renumbering, reference or wording cleanup with no new safety "
    "meaning). Be conservative: if the meaning is unchanged, answer editorial. Return only the "
    "requested fields."
)

JUDGE_SYSTEM = (
    "You check whether a generic drug label contains the same safety information as a brand "
    "label. You get one CLAIM from the brand label and up to 5 numbered candidate UNITS from the "
    "generic label.\n"
    "Rules:\n"
    "1. propagated: the generic units state the same safety meaning; wording may differ.\n"
    "2. partial: some but not all elements of the claim are present (for example the warning "
    "but not the affected population).\n"
    "3. not_propagated: none of the units carry the claim.\n"
    "4. insufficient_evidence: the units are unrelated or unclear.\n"
    "Quote only text that appears word for word in the units. Never paraphrase inside quotes. "
    "Decide only from the supplied text, not from outside medical knowledge. Do not give "
    "medical advice."
)

ASSISTANT_SYSTEM = (
    "You answer questions about label lag data for US generic drug labels, using only the "
    "results of your tools. If a question asks for medical advice, dosing or whether to take a "
    "drug, reply with a short neutral refusal and suggest asking a pharmacist or doctor. Always "
    "cite events or judgements by id. Never use the words violation, non-compliant or unsafe. "
    "Whenever you give a lag number, add that dates are label publication dates, not the dates "
    "companies made the change. Keep the answer under 120 words. If tools return nothing, say "
    "so."
)


def classify_user(section_key: str, change_kind: str, new_unit: str, old_unit: str | None) -> str:
    lines = [f"SECTION: {section_key}", f"CHANGE: {change_kind}"]
    if old_unit:
        lines.append(f"BEFORE: {old_unit}")
    lines.append(f"AFTER: {new_unit}")
    return "\n".join(lines)


def judge_user(claim: str, brand_unit: str, units: list[str]) -> str:
    numbered = "\n".join(f"UNIT {i}: {u}" for i, u in enumerate(units, start=1))
    return f"CLAIM: {claim}\nBRAND TEXT: {brand_unit}\n{numbered or 'UNIT 1: (none)'}"
