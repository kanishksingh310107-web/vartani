"""The multiple-choice prompt. Same wording as the paper's notebook so results stay comparable."""
LETTERS = ["A", "B", "C", "D"]
INSTRUCTION = ("Read the passage and answer the multiple-choice question. "
               "Reply with only the letter of the correct option (A, B, C or D).")


def format_prompt(t: dict) -> str:
    opts = "\n".join(f"{l}) {o}" for l, o in zip(LETTERS, t["options"]))
    parts = [INSTRUCTION]
    if t.get("passage", "").strip():
        parts.append(f"Passage:\n{t['passage']}")
    parts += [f"Question:\n{t['question']}", f"Options:\n{opts}"]
    return "\n\n".join(parts)
