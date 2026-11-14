AVAILABLE = False
VERSION = "none"
N_FEATURES = 10
N_CLASSES = 4
CLASS_LABEL = (0, 1, 2, 3)
CLASS_NAME = ("Normal", "Advisory", "Warning", "Danger")


def predict_proba(x):
    return 0, [1.0, 0.0, 0.0, 0.0]
