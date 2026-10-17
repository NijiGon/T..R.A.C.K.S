from tests.simulate import Conditions, evaluate

# Line margin, inheritance and duplicate settings the counter ships with (see krl/config.py and krl/counting.py)
MARGIN = 40
INHERIT_FRAMES = 30
DUPLICATE_IOU = 0.5


def test_default_conditions_count_nearly_every_crossing():
    accuracy, errors, crossings = evaluate(Conditions(), MARGIN, INHERIT_FRAMES, DUPLICATE_IOU, seeds=range(4))
    assert crossings > 150  # four seeds of 60 people each
    assert accuracy >= 0.99, f"{errors} errors in {crossings} crossings"


def test_clean_conditions_count_every_crossing():
    clean = Conditions(noise_px=0.0, miss_prob=0.0, id_switch_prob=0.0, duplicate_prob=0.0,
                       linger_prob=0.0, turnback_prob=0.0)
    accuracy, errors, _ = evaluate(clean, MARGIN, INHERIT_FRAMES, DUPLICATE_IOU, seeds=range(4))
    assert errors == 0
