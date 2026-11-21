# ruff: noqa: E501
"""Lesson 3 answer keys, written 2026-11-20 BEFORE any lesson 3 run.

They SCORE answers. They are never put in a prompt. A regex key is a screen:
the best and the worst answers of each task are also read by hand.
"""

# summary: (artifact, case-insensitive regexes; each one found = one point)
SUMMARY = {
    "quora_paper": [
        r"quora",
        r"duplicate|paraphrase|same meaning",
        r"siamese|twin|shared encoder",
        r"lstm|recurrent",
        r"attention",
    ],
    "quora_code": [
        r"quora|duplicate|question pair",
        r"lstm|recurrent",
        r"attention",
        r"train",
    ],
    "adam_code": [
        r"adam",
        r"optimi[sz]",
        r"moment|beta",
        r"weight.?decay|amsgrad|bias.?correct",
    ],
    "otp_code": [
        r"one.?time|otp",
        r"hotp|totp",
        r"hmac|secret|key",
        r"go\b|golang|package|valid",
    ],
}

# rewrite: (question, history, last answer, regexes the rewrite must ALL match)
REWRITE = [
    (
        "Explain the second one.",
        ["Compare these and explain why the results diverge."],
        "Main differences: 1. CLIP_NORM is 1.5 in B and 1.0 in A. 2. Label smoothing is 0.05 in B and 0.1 in A. 3. Weight decay is 1e-3 in B and 0.01 in A.",
        [r"label.?smoothing"],
    ),
    (
        "Why is that a problem?",
        ["What is wrong in my code?"],
        "The biggest problem: pos_class_weight() is defined and never called, so the loss is not weighted for class imbalance.",
        [r"pos_class_weight|class.?weight|imbalanc"],
    ),
    (
        "What learning rate does B_train.py use?",
        ["Compare these and explain why the results diverge."],
        "B differs from A in clipping, label smoothing and weight decay.",
        [r"learning.?rate", r"B_train|code|B\b"],
    ),
    (
        "Fix it.",
        ["Find the bugs in the TOTP code."],
        "Y1: the dynamic truncation offset is masked with 0x7, but RFC 4226 says the low 4 bits (0xf).",
        [r"0x7|0xf|offset|truncat"],
    ),
    (
        "And in the paper?",
        ["What is the batch size in the code?"],
        "The code uses BATCH_SIZE = 64.",
        [r"batch.?size", r"paper|\bA\b|reference"],
    ),
    (
        "Show me the code for that.",
        ["Why is the F1 score optimistic?"],
        "The threshold is re-tuned on the validation set inside evaluate(), and the same set is then reported.",
        [r"threshold", r"code|evaluate"],
    ),
    (
        "Compare these and explain why the results diverge.",
        ["What does the code do?"],
        "",
        [r"compare|diverge", r"explain|why"],
    ),
    (
        "Does it also shuffle the test set?",
        ["How does B load the data?"],
        "B builds a DataLoader for train with shuffle=True and one for validation.",
        [r"shuffl", r"test"],
    ),
]

# fresh: the 12 yes/no questions of slice 10 (31.14). The statement must keep
# the subject (all regexes) and must not be a question.
FRESH = [
    ("Does the code check that beta1 is below 1?", [r"beta1|beta 1|betas\[0\]"]),
    ("Does the code raise an error if eps is negative?", [r"eps|epsilon"]),
    (
        "Does the code raise an error when the learning rate is negative?",
        [r"learning.?rate|\blr\b"],
    ),
    ("Does the code handle complex parameters in a special way?", [r"complex"]),
    ("Does the code convert an old float step counter into a tensor?", [r"step"]),
    ("Does the code clip the gradient norm?", [r"clip|norm"]),
    ("Does the code ever use a random number?", [r"random"]),
    ("Does the code log or print anything?", [r"log|print"]),
    (
        "Does the code check that beta2 is strictly below 1?",
        [r"beta2|beta 2|betas\[1\]"],
    ),
    (
        "Does the code support a learning rate schedule inside the optimizer?",
        [r"schedul"],
    ),
    (
        "Does the code add the weight decay term to the gradient with a plus sign?",
        [r"weight.?decay"],
    ),
    (
        "Does the code allow a tensor learning rate when foreach is true and capturable is false?",
        [r"tensor", r"foreach|capturable"],
    ),
]

# chat: (question, regexes that must ALL match, max characters)
CHAT = [
    ("What is HMAC, in two sentences?", [r"hash", r"key|secret"], 900),
    (
        "Write a Python function that returns the n-th Fibonacci number with a loop.",
        [r"def ", r"for |while "],
        4000,
    ),
    (
        "What is the difference between a list and a tuple in Python?",
        [r"mutable|immutable|change"],
        3000,
    ),
    (
        "Explain what a learning rate is in one short paragraph.",
        [r"step|update", r"gradient|loss|weight"],
        1500,
    ),
    (
        "What does git rebase do, briefly?",
        [r"commit", r"base|replay|re-?appl|on top|move"],
        1500,
    ),
    ("Hello!", [r"\w"], 600),
]

# respond_two, quora pair (EXPECTED.md, weights of the impact column)
STORY_QUORA = [
    ("11", 3, (r"stop ?words?", r"mask|attention|attend|exclud")),
    (
        "6",
        3,
        (
            r"pos_class_weight|class.weight|pos_weight|imbalanc",
            r"never|not (used|called|applied)|unused|ignored|missing",
        ),
    ),
    ("1", 3, (r"project", r"pool|weighted sum|hidden state|sum")),
    ("9", 3, (r"threshold", r"validation|val\b|same|leak|optimistic|tuned|re-?select")),
    ("10b", 3, (r"0\.9439|0\.8226|overfit|12\.\d|12-point|12 point",)),
    ("2", 2, (r"clip", r"1\.5")),
    ("3", 2, (r"label.?smoothing|LABEL_SMOOTHING", r"0\.05")),
    ("4", 2, (r"weight.?decay", r"1e-3|0\.001")),
    ("5", 2, (r"unfreez", r"epoch")),
    ("7", 2, (r"warm.?up", r"no |missing|absent|ReduceLROnPlateau|plateau|not ")),
    ("8", 2, (r"test", r"no |without|missing|only|single|held.?out|never")),
    ("10", 2, (r"seed|determinis|cudnn",)),
    ("12", 2, (r"punctuation|<UNK>|\bunk\b|unknown", r"mask|exclud")),
    ("13", 2, (r"cosine", r"feature|extra|append|3073|concat")),
    ("14", 2, (r"20,?000|vocab", r"cap|limit|oov|unknown|<unk>|unk|whitespace")),
    (
        "17",
        2,
        (r"requires_grad", r"param.?group|optimizer|no effect|ignored|does nothing"),
    ),
    (
        "18",
        2,
        (r"stop ?word|mask", r"all|every|only|entire", r"zero|nan|uniform|empty|-inf"),
    ),
]
