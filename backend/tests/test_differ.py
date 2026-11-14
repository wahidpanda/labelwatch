from app.detect.differ import diff_units, similarity


def test_identical_sections_have_no_changes() -> None:
    units = ["Bleeding risk.", "Monitor INR."]
    assert diff_units(units, list(units)) == []


def test_whitespace_and_case_only_is_not_a_change() -> None:
    assert diff_units(["Monitor  INR regularly."], ["monitor INR   regularly."]) == []


def test_reordered_units_are_not_changes() -> None:
    assert diff_units(["A warning.", "B warning."], ["B warning.", "A warning."]) == []


def test_added_unit() -> None:
    changes = diff_units(
        ["Bleeding risk."],
        [
            "Bleeding risk.",
            "Neuropsychiatric events have been reported, including suicidal thoughts.",
        ],
    )
    assert [c.kind for c in changes] == ["added"]
    assert changes[0].new is not None
    assert changes[0].new.startswith("Neuropsychiatric")


def test_small_edit_is_modified_and_large_edit_is_added_plus_removed() -> None:
    old = ["Serious neuropsychiatric events have been reported in patients taking this drug."]
    small = ["Serious neuropsychiatric events have been reported in patients taking this drug!"]
    changes = diff_units(old, small)
    assert [c.kind for c in changes] == ["modified"]
    assert changes[0].similarity >= 0.9

    big = ["Hepatic failure requiring transplant occurred in two patients."]
    kinds = sorted(c.kind for c in diff_units(old, big))
    assert kinds == ["added", "removed"]


def test_removed_unit() -> None:
    changes = diff_units(["Keep.", "Old note."], ["Keep."])
    assert [(c.kind, c.old) for c in changes] == [("removed", "Old note.")]


def test_similarity_is_normalised() -> None:
    assert similarity("Monitor INR", "monitor   inr") == 1.0
