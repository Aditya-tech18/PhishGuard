"""Strict numeric JSON inference for five sklearn classifier families.

Artifacts contain no Python objects, import paths or executable expressions. Validation
bounds tree sizes and rejects cycles, malformed topology and non-finite parameters before
serving. This is format validation, not an authenticity signature: deploy trusted artifacts.
"""

from collections import Counter
import math
import numpy as np
from phishguard.features.feature_schema import FEATURE_NAMES

ALGORITHMS = {
    "logistic_regression",
    "decision_tree",
    "random_forest",
    "gradient_boosting",
    "gaussian_naive_bayes",
}
MAX_TREES = 256
MAX_TOTAL_NODES = 500_000
MAX_DEPTH = 128


def finite_array(value, shape=None):
    array = np.asarray(value, dtype=float)
    if not np.isfinite(array).all() or (shape is not None and array.shape != shape):
        raise ValueError("Invalid parameter shape or non-finite numeric parameter")
    return array


def sigmoid(value):
    return 1.0 / (1.0 + math.exp(-float(np.clip(value, -500, 500))))


class Tree:
    """Validated binary tree with bounded iterative traversal, including leaf values."""

    def __init__(self, document, probability=True):
        self.left = self._integers(document.get("left"))
        self.right = self._integers(document.get("right"))
        self.features = self._integers(document.get("features"))
        self.values = finite_array(document.get("values"))
        self.thresholds = finite_array(document.get("thresholds"))
        size = len(self.left)
        if not 1 <= size <= MAX_TOTAL_NODES:
            raise ValueError("Tree node count exceeds limits")
        if any(len(a) != size for a in [self.right, self.features, self.values, self.thresholds]):
            raise ValueError("Tree arrays must have identical lengths")
        if self.values.ndim != 1 or self.thresholds.ndim != 1:
            raise ValueError("Tree numeric arrays must be one dimensional")
        seen = set()
        stack = [(0, 0)]
        while stack:
            node, depth = stack.pop()
            if node in seen or depth > MAX_DEPTH:
                raise ValueError("Tree contains cycles, shared nodes or excessive depth")
            seen.add(node)
            left, right, feature = self.left[node], self.right[node], self.features[node]
            if left == right == -1:
                if probability and not 0 <= self.values[node] <= 1:
                    raise ValueError("Leaf probability outside [0,1]")
                if feature != -2:
                    raise ValueError("Invalid leaf feature sentinel")
                continue
            if not (0 <= left < size and 0 <= right < size and left != right):
                raise ValueError("Invalid child node index")
            if not 0 <= feature < len(FEATURE_NAMES):
                raise ValueError("Invalid feature index")
            stack.extend([(left, depth + 1), (right, depth + 1)])
        if len(seen) != size:
            raise ValueError("Unreachable nodes are forbidden")
        self.size = size

    @staticmethod
    def _integers(value):
        if not isinstance(value, list) or any(type(x) is not int for x in value):
            raise ValueError("Tree indices must be JSON integers")
        return value

    def predict(self, x):
        node = 0
        path = []
        for _ in range(MAX_DEPTH + 1):
            if self.left[node] == -1:
                return float(self.values[node]), path
            feature = self.features[node]
            path.append(feature)
            # sklearn trees compare float32 input against float64 thresholds.
            value = float(np.float32(x[feature]))
            node = self.left[node] if value <= self.thresholds[node] else self.right[node]
        raise RuntimeError("Validated tree traversal exceeded its depth")


class PortableClassifier:
    def __init__(self, algorithm, parameters):
        if algorithm not in ALGORITHMS:
            raise ValueError("Unsupported portable classifier")
        self.algorithm = algorithm
        self.parameters = parameters
        n = len(FEATURE_NAMES)
        if algorithm == "logistic_regression":
            self.weights = finite_array(parameters["weights"], (n,))
            self.bias = float(parameters["bias"])
            if not math.isfinite(self.bias):
                raise ValueError("Invalid logistic bias")
        elif algorithm == "gaussian_naive_bayes":
            self.means = finite_array(parameters["means"], (2, n))
            self.variances = finite_array(parameters["variances"], (2, n))
            self.priors = finite_array(parameters["priors"], (2,))
            if (self.variances <= 0).any() or (self.priors <= 0).any():
                raise ValueError("Naive Bayes variances and priors must be positive")
            if not np.isclose(self.priors.sum(), 1):
                raise ValueError("Class priors must sum to one")
        else:
            documents = parameters.get("trees")
            if not isinstance(documents, list) or not 1 <= len(documents) <= MAX_TREES:
                raise ValueError("Invalid tree ensemble size")
            if algorithm == "decision_tree" and len(documents) != 1:
                raise ValueError("Decision tree classifier needs exactly one tree")
            self.trees = [
                Tree(tree, probability=algorithm != "gradient_boosting") for tree in documents
            ]
            if sum(tree.size for tree in self.trees) > MAX_TOTAL_NODES:
                raise ValueError("Ensemble exceeds total node limit")
            if algorithm == "gradient_boosting":
                self.initial = float(parameters["initial_log_odds"])
                self.learning_rate = float(parameters["learning_rate"])
                if not math.isfinite(self.initial) or not 0 < self.learning_rate <= 1:
                    raise ValueError("Invalid gradient boosting parameters")

    def predict(self, x):
        x = finite_array(x, (len(FEATURE_NAMES),))
        if self.algorithm == "logistic_regression":
            contributions = x * self.weights
            probability = sigmoid(float(contributions.sum()) + self.bias)
            order = np.argsort(contributions)[::-1]
            reasons = [FEATURE_NAMES[i] for i in order if contributions[i] > 0][:4]
        elif self.algorithm == "gaussian_naive_bayes":
            terms = -0.5 * (
                np.log(2 * np.pi * self.variances) + ((x - self.means) ** 2) / self.variances
            )
            logp = terms.sum(axis=1) + np.log(self.priors)
            probability = sigmoid(logp[1] - logp[0])
            evidence = terms[1] - terms[0]
            order = np.argsort(evidence)[::-1]
            reasons = [FEATURE_NAMES[i] for i in order if evidence[i] > 0][:4]
        else:
            values, features = [], Counter()
            for tree in self.trees:
                value, path = tree.predict(x)
                values.append(value)
                features.update(set(path))
            probability = (
                sigmoid(self.initial + self.learning_rate * sum(values))
                if self.algorithm == "gradient_boosting"
                else float(np.mean(values))
            )
            reasons = [FEATURE_NAMES[index] for index, _ in features.most_common(4)]
        return probability, reasons


def export_tree(estimator, probability=True):
    tree = estimator.tree_
    raw = tree.value[:, 0, :]
    if probability:
        total = raw.sum(axis=1)
        if raw.shape[1] != 2 or (total <= 0).any():
            raise ValueError("Binary classifier tree required")
        values = raw[:, 1] / total
    else:
        values = raw[:, 0]
    return {
        "left": tree.children_left.tolist(),
        "right": tree.children_right.tolist(),
        "features": tree.feature.tolist(),
        "thresholds": tree.threshold.tolist(),
        "values": values.tolist(),
    }


def export_parameters(estimator, algorithm):
    if list(estimator.classes_) != [0, 1]:
        raise ValueError("Export requires ordered classes [0,1]")
    if algorithm == "logistic_regression":
        return {"weights": estimator.coef_[0].tolist(), "bias": float(estimator.intercept_[0])}
    if algorithm == "gaussian_naive_bayes":
        return {
            "means": estimator.theta_.tolist(),
            "variances": estimator.var_.tolist(),
            "priors": estimator.class_prior_.tolist(),
        }
    if algorithm == "decision_tree":
        return {"trees": [export_tree(estimator)]}
    if algorithm == "random_forest":
        return {"trees": [export_tree(tree) for tree in estimator.estimators_]}
    if algorithm == "gradient_boosting":
        prior = estimator.init_.class_prior_
        return {
            "trees": [export_tree(tree[0], probability=False) for tree in estimator.estimators_],
            "initial_log_odds": float(np.log(prior[1] / prior[0])),
            "learning_rate": float(estimator.learning_rate),
        }
    raise ValueError("Unsupported estimator family")
