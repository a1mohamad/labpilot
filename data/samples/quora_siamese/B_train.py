"""Quora Question Pairs - LSTM + MultiHead Bahdanau attention, siamese setup.

Flattened from the research notebooks (01-tokenizer, 02-train) into one script
so the whole pipeline can be run headless.

DATA
    pairs                 404,290   (255,027 not duplicate / 149,263 duplicate)
    positive rate         36.92%
    empty rows removed    3
    unique tokens         103,212   (vocab capped at 20,000)
    GloVe coverage        18,604 / 20,000 = 93.02%
    unknown token ratio   0.0049
    train / val batches   2,843 / 316 at batch size 128

MODEL
    total parameters      11,633,737
    trainable parameters   9,633,737   (2,000,000 embedding params frozen at start)

RUN SUMMARY (MLflow run LSTM_attention-MultiHead-Bahdanau-v10, GTX 1650)
    early stopped at      epoch 15 of 50
    best checkpoint       epoch 14
    lr reduced            3e-4 -> 1.5e-4 at epoch 13 (ReduceLROnPlateau)

    epoch 15 train        loss 0.2723 | acc 0.9581 | P 0.9333 | R 0.9548 | F1 0.9439 | AUROC 0.9891
    epoch 15 val          loss 0.3425 | acc 0.8667 | P 0.8084 | R 0.8373 | F1 0.8226 | AUROC 0.9263

    best (epoch 14) val   loss 0.3417 | acc 0.8649 | P 0.7869 | R 0.8696 | F1 0.8262 | AUROC 0.9272
    final threshold       0.4631  (re-selected on the validation set after reloading the checkpoint)

    per-epoch "optimal" threshold, epochs 10-15:
        0.4358, 0.3970, 0.4825, 0.3893, 0.4631, 0.5787
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import inspect
import json
import logging
import os
from pathlib import Path
import random
import re
import shutil

import mlflow
import nltk
from nltk.corpus import stopwords
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
import torch
from torch import nn
from torch.amp import GradScaler, autocast
from torch.cuda import Event
import torch.nn.functional as F
from torch.nn.utils import clip_grad_norm_
from torch.optim.lr_scheduler import (
    CosineAnnealingLR,
    CosineAnnealingWarmRestarts,
    OneCycleLR,
    ReduceLROnPlateau,
)
from torch.utils.data import DataLoader, Dataset
from torchmetrics.classification import (
    AUROC,
    AveragePrecision,
    BinaryAccuracy,
    BinaryF1Score,
    BinaryPrecision,
    BinaryRecall,
    PrecisionRecallCurve,
)
from tqdm import tqdm

nltk.download("stopwords", quiet=True)


class SystemConfig:
    IS_DETERMINISTIC = False
    _PROJECT_ROOT = Path.cwd()
    _DB_PATH = _PROJECT_ROOT / "mlflow-quora-questions-pairs.db"
    MLFLOW_TRACKING_URI = f"sqlite:///{_DB_PATH.as_posix()}"
    NEXT_LINE_COUNTER = 180
    SEED = 28
    USED_SCALER = False

    @staticmethod
    def get_device():
        """Detects the best available device. Priority: TPU -> GPU -> CPU."""
        try:
            import torch_xla.core.xla_model as xm

            device = xm.xla_device()
            print(f">>> Using TPU: {device}")
        except ImportError:
            if torch.cuda.is_available():
                device = torch.device("cuda")
                print(f">>> Using GPU: {torch.cuda.get_device_name(0)}")
            else:
                device = torch.device("cpu")
                print(">>> Using CPU")
        return device

    DEVICE = get_device.__func__()

    @classmethod
    def to_dict(cls):
        return {
            k.lower(): v
            for k, v in cls.__dict__.items()
            if not k.startswith("_")
            and not inspect.isroutine(v)
            and not isinstance(v, (classmethod, staticmethod))
        }


class PathConfig:
    ROOT_DIR = Path().cwd()
    EMB_DIR = ROOT_DIR.parent.parent
    EMB_PATH = EMB_DIR / "glove.6B.100d.txt"
    ARTIFACT_DIR = ROOT_DIR / "artifacts"
    DATA_DIR = ROOT_DIR / "data" / "raw"
    MLFLOW_DIR = ROOT_DIR / "mlruns"
    CHECKPOINT_DIR = ARTIFACT_DIR / "checkpoint"
    CONFIG_PATH = ARTIFACT_DIR / "configs.json"
    VOCABS_PATH = ARTIFACT_DIR / "vocabs.json"
    LABEL_MAPPING_PATH = ARTIFACT_DIR / "label_mapping.json"
    TRAIN_CSV_PATH = DATA_DIR / "train.csv"

    @classmethod
    def to_dict(cls):
        return {
            k.lower(): v
            for k, v in cls.__dict__.items()
            if not k.startswith("_")
            and not inspect.isroutine(v)
            and not isinstance(v, (classmethod, staticmethod))
        }


class TokenConfig:
    PAD_TOKEN = "<PAD>"
    UNK_TOKEN = "<UNK>"
    PAD_IDX = 0
    UNK_IDX = 1
    LOWERCASE = True
    UPPERCASE = False
    MAX_LENGTH = 50
    VOCAB_SIZE = 20000

    @classmethod
    def to_dict(cls):
        return {
            k.lower(): v
            for k, v in cls.__dict__.items()
            if not k.startswith("_")
            and not inspect.isroutine(v)
            and not isinstance(v, (classmethod, staticmethod))
        }


class LoaderConfig:
    BATCH_SIZE = 128
    NUM_WORKERS = 0
    IS_PIN_MEMORY = True

    @classmethod
    def to_dict(cls):
        return {
            k.lower(): v
            for k, v in cls.__dict__.items()
            if not k.startswith("_")
            and not inspect.isroutine(v)
            and not isinstance(v, (classmethod, staticmethod))
        }


class ModelConfig:
    MODEL_TYPE = "LSTM_attention"
    ATTENTION_TYPE = "MultiHead-Bahdanau"
    TOKENIZER_TYPE = "Whitespace"
    # Embedding
    LAYER_NORM_EMB = False
    FREEZE_TOKEN_EMBEDDING = True
    TOKEN_EMBEDDING = "gloVe-6B-100d"
    EMB_DIM = 100
    EMB_DP = 0.0
    # Model
    LOSS = "BCE with Logits"
    NUM_HEADS = 4
    BIDIRECTIONAL = True
    DROPOUT = 0.35
    HIDDEN_DIM = 384
    LSTM_OUT = HIDDEN_DIM * (2 if BIDIRECTIONAL else 1)
    ATTENTION_DROPOUT = 0.0
    LAYER_NORM_LSTM = False
    LAYER_NORM_ATTENTION = False
    ATTENTION_PROJECTION = False
    if ATTENTION_PROJECTION:
        PROJECT_DIM = HIDDEN_DIM // 2
    ENC_DIM = PROJECT_DIM if ATTENTION_PROJECTION else LSTM_OUT
    if LOSS == "Contrastive Loss":
        MARGIN = 1.0
    elif LOSS == "BCE with Logits":
        LABEL_SMOOTHING = 0.05
        FC_DIMS = [1024, 256]
        FC_DP = 0.4
        SIAMESE_SIMILARITY_PARM = [
            "Encoded Q1",
            "Encoded Q2",
            "Multiplication Q1, Q2",
            "Abs Subtract Q1, Q2",
            "Cosine Similarity",
        ]
        MULTIPLE_FC_PARAM = sum(
            1 for param in SIAMESE_SIMILARITY_PARM if "Q1" in param or "Q2" in param
        )
        INPUT_FC_DIM = MULTIPLE_FC_PARAM * ENC_DIM
        if any("Cosine" in param for param in SIAMESE_SIMILARITY_PARM):
            INPUT_FC_DIM += 1
    MASK_FILL_NUM = -1e10
    NUM_LAYERS = 2
    SKIP_CONNECTION = False

    @classmethod
    def to_dict(cls):
        return {
            k.lower(): v
            for k, v in cls.__dict__.items()
            if not k.startswith("_")
            and not inspect.isroutine(v)
            and not isinstance(v, (classmethod, staticmethod))
        }


class TrainConfig:
    LOSS = "BCE with Logits"
    CLIP_NORM = 1.5
    EARLY_STOP_METRIC = "loss"
    CHECKPOINT_METRIC = "F1Score"
    if CHECKPOINT_METRIC == "loss":
        CHECKPOINT_MODE = "min"
    else:
        CHECKPOINT_MODE = "max"
    SCHEDULER_METRIC = "loss"
    EARLY_STOP_MIN_DELTA = 1e-4
    if EARLY_STOP_METRIC in ["F1Score", "Accuracy", "Precision", "Recall"]:
        EARLY_STOP_MODE = "max"
    elif EARLY_STOP_METRIC == "loss":
        EARLY_STOP_MODE = "min"
    EARLY_STOP_PATIENCE = 5
    EPOCHS = 50
    LEARNING_RATE = 3e-4
    METRICS_THRESHOLD = 0.5
    TRAIN_TEST_SPLIT = 0.9
    UNFREEZE_EPOCH = 3
    WEIGHT_DECAY = 1e-3
    SCHEDULER_TYPE = "ReduceLROnPlateau"
    if SCHEDULER_TYPE == "ReduceLROnPlateau":
        SCHEDULER_FACTOR = 0.5
        SCHEDULER_MIN_LR = 1e-7
        SCHEDULER_PATIENCE = 2
        SCHEDULER_THRESHOLD = 0.01
        SCHEDULER_THRESHOLD_MODE = "rel"
        if SCHEDULER_METRIC in ["F1Score", "Accuracy", "Precision", "Recall"]:
            SCHEDULER_MODE = "max"
        elif SCHEDULER_METRIC == "loss":
            SCHEDULER_MODE = "min"
    elif SCHEDULER_TYPE == "CosineAnnealing":
        SCHEDULER_ETA_MIN = 1e-6
    elif SCHEDULER_TYPE == "CosineAnnealingWarmRestarts":
        SCHEDULER_T_0 = 5
        SCHEDULER_T_MULT = 2
        SCHEDULER_ETA_MIN = 1e-6
    elif SCHEDULER_TYPE == "OneCycleLR":
        SCHEDULER_PCT_START = 0.3
        SCHEDULER_DIV_FACTOR = 25
        SCHEDULER_FINAL_DIV_FACTOR = 100

    @classmethod
    def to_dict(cls):
        return {
            k.lower(): v
            for k, v in cls.__dict__.items()
            if not k.startswith("_")
            and not inspect.isroutine(v)
            and not isinstance(v, (classmethod, staticmethod))
        }


sys_cfg = SystemConfig()
path_cfg = PathConfig()
token_cfg = TokenConfig()
train_cfg = TrainConfig()
loader_cfg = LoaderConfig()
model_cfg = ModelConfig()


def seed_everything(seed, deterministic=False):
    """Ensures absolute reproducibility."""
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

    if deterministic:
        # Only use these for the final "Gold" run to ensure exact results
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        print(">>> Using STRICT Deterministic mode (Slower).")
    else:
        # Benchmark=True allows cuDNN to find the fastest kernels for your hardware
        torch.backends.cudnn.deterministic = False
        torch.backends.cudnn.benchmark = True
        print(">>> Using PROTOTYPING mode (Faster).")
    print(f">>> For Reproducibility, Everything seeded with {seed}!")


def set_scaler(config=SystemConfig):
    if config.USED_SCALER:
        scaler = GradScaler(
            device=sys_cfg.DEVICE.type, enabled=(sys_cfg.DEVICE.type == "cuda")
        )
        print(">>> Scaler used in training")
    else:
        scaler = None
        print(">>> Scaler is not Used")
    return scaler


def clean_artifact_directory(artifact_dir: Path):
    if artifact_dir.exists():
        shutil.rmtree(artifact_dir)
        print(f">>> Cleaned local artifact directory: {artifact_dir}")
    artifact_dir.mkdir(parents=True, exist_ok=True)


def get_serializable_configs(configs_dict):
    """Create a JSON-serializable version of configs"""
    serializable = {}
    for section, params in configs_dict.items():
        if section not in ["system", "path"]:
            serializable[section] = params
            continue

        serializable[section] = {}
        for key, value in params.items():
            if isinstance(value, torch.device):
                serializable[section][key] = str(value)
            elif isinstance(value, Path):
                serializable[section][key] = str(value)
            elif key == "device":
                serializable[section][key] = (
                    str(value) if value.type == "cuda" else "cpu"
                )
            else:
                serializable[section][key] = value
    return serializable


def configs_dict(config_path):
    configs = {}
    configs_names = [
        SystemConfig,
        PathConfig,
        TokenConfig,
        LoaderConfig,
        TrainConfig,
        ModelConfig,
    ]
    for config in configs_names:
        cfg_clean = f"{config.__name__.replace('Config', '').lower()}"
        configs[cfg_clean] = config.to_dict()

    serializable_configs = get_serializable_configs(configs)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(serializable_configs, f, ensure_ascii=False, indent=2)
    print(">>> Configs Saved as JSON File!")
    return configs


class QuoraPreproccesor:
    def __init__(self, config=token_cfg):
        self.config = config

    def _clean_text(self, text):
        if self.config.LOWERCASE:
            text = text.lower()
        if self.config.UPPERCASE:
            text = text.upper()

        text = re.sub(r"!", " ! ", text)
        text = re.sub(r"\?", " ? ", text)
        text = re.sub(r"\.", " . ", text)
        text = re.sub(r",", " , ", text)
        text = re.sub(r"-", " - ", text)
        text = re.sub(r"\(", " ( ", text)
        text = re.sub(r"\)", " ) ", text)
        text = re.sub(r"\"", " ' ", text)
        text = re.sub(r"\\", " \\ ", text)
        text = re.sub(r"/", " / ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def preprocess_df(self, df):
        df = df.copy()

        df["question1"] = df["question1"].fillna("")
        df["question2"] = df["question2"].fillna("")

        df["question1"] = df["question1"].apply(self._clean_text)
        df["question2"] = df["question2"].apply(self._clean_text)
        before = len(df)
        df = df[
            (df["question1"].str.strip() != "") & (df["question2"].str.strip() != "")
        ].reset_index(drop=True)
        after = len(df)
        print(f">>> Preprocessing complete! Removed empty rows: {before - after}")

        return df


class QuoraTokenizer:
    def __init__(self, config=token_cfg):
        self.config = config
        self.vocabs = {}
        self.idx2word = {}
        self.stop_mask = None
        self.vocab_size = config.VOCAB_SIZE

    def build_vocabs(self, df):
        counter = Counter()
        for q1, q2 in zip(df["question1"], df["question2"]):
            counter.update(q1.split())
            counter.update(q2.split())
        most_common = counter.most_common(self.config.VOCAB_SIZE - 2)
        self.vocabs = {
            self.config.PAD_TOKEN: self.config.PAD_IDX,
            self.config.UNK_TOKEN: self.config.UNK_IDX,
        }
        for idx, (word, _) in enumerate(most_common, start=2):
            self.vocabs[word] = idx
        self.idx2word = {v: k for k, v in self.vocabs.items()}
        self.vocab_size = len(self.vocabs)
        self._build_stop_mask()
        print(">>> Vocabs created!")

    def _build_stop_mask(self):
        stop_set = set(stopwords.words("english"))
        custom = {
            "?",
            "!",
            ".",
            ",",
            "-",
            "...",
            "..",
            "/",
            "\\",
            "(",
            ")",
            '"',
            "'",
            "<PAD>",
            "what's",
            "<UNK>",
        }
        stop_set.update(custom)

        mask = torch.ones(len(self.vocabs))
        for word, idx in self.vocabs.items():
            if word in stop_set:
                mask[idx] = 0.0
        self.stop_mask = mask

    def encode(self, text):
        tokens = text.split()
        ids = [self.vocabs.get(t, self.vocabs[self.config.UNK_TOKEN]) for t in tokens]
        ids = ids[: self.config.MAX_LENGTH]
        ids += [self.vocabs[self.config.PAD_TOKEN]] * (
            self.config.MAX_LENGTH - len(ids)
        )
        return ids

    def decode(self, ids, remove_pad=True):
        pad_id = self.vocabs[self.config.PAD_TOKEN]
        return " ".join(
            self.idx2word.get(i, self.config.UNK_TOKEN)
            for i in ids
            if not (remove_pad and i == pad_id)
        )

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "max_length": self.config.MAX_LENGTH,
            "vocab_size": self.vocab_size,
            "special_tokens": {
                "pad": self.config.PAD_TOKEN,
                "unk": self.config.UNK_TOKEN,
            },
            "vocabs": self.vocabs,
            "idx2word": {str(k): v for k, v in self.idx2word.items()},
            "stop_mask": self.stop_mask.tolist() if self.stop_mask is not None else None,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f">>> Tokenizer saved to {path}")

    def save_label_mapping(self, path):
        path = Path(path)
        label_mapping = {"0": "different", "1": "duplicated"}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(label_mapping, f, ensure_ascii=False, indent=2)
            print(">>> Label mapping saved!")

    def load_embedding(self, emb_dim, emb_dir):
        vocab_size = len(self.vocabs)
        emb_matrix = np.random.normal(0.0, 0.05, (vocab_size, emb_dim)).astype(
            np.float32
        )

        # PAD should be zero vector
        pad_idx = self.vocabs[self.config.PAD_TOKEN]
        emb_matrix[pad_idx] = np.zeros(emb_dim, dtype=np.float32)

        found = 0
        with open(emb_dir, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                word = parts[0]
                vector = np.array(parts[1:], dtype=np.float32)

                if len(vector) != emb_dim:
                    continue

                if word in self.vocabs:
                    idx = self.vocabs[word]
                    emb_matrix[idx] = vector
                    found += 1

        print(f">>> Loaded GloVe vectors: {found}/{vocab_size}")
        print(f">>> Coverage: {found / vocab_size:.2%}")

        return torch.FloatTensor(emb_matrix)


class QuoraDataset(Dataset):
    def __init__(self, df, tokenizer):
        self.q1 = df["question1"].values
        self.q2 = df["question2"].values
        self.label = df["is_duplicate"].values
        self.tokenizer = tokenizer

    def __len__(self):
        return len(self.q1)

    def pos_class_weight(self, device):
        pos_num = (self.label == 1).sum()
        neg_num = (self.label == 0).sum()
        pos_weight = torch.tensor(neg_num / pos_num).to(device)
        return pos_weight

    def __getitem__(self, idx):
        encoded_q1 = self.tokenizer.encode(self.q1[idx])
        encoded_q2 = self.tokenizer.encode(self.q2[idx])
        label = self.label[idx]

        return {
            "q1": torch.LongTensor(encoded_q1),
            "q2": torch.LongTensor(encoded_q2),
            "label": torch.tensor(label, dtype=torch.float),
        }


class AttentionHead(nn.Module):
    def __init__(
        self,
        hidden_dim,
        proj_dim,
        mask_fill_num=model_cfg.MASK_FILL_NUM,
        dropout=model_cfg.ATTENTION_DROPOUT,
    ):
        super().__init__()
        self.W = nn.Linear(hidden_dim, proj_dim)  # project to subspace
        self.V = nn.Linear(proj_dim, 1, bias=False)  # score
        self.mask_fill_num = mask_fill_num
        self.dropout = nn.Dropout(dropout)

    def forward(self, lstm_output, mask):
        proj = self.W(lstm_output)  # [B, L, proj_dim]
        energy = torch.tanh(proj)
        scores = self.V(energy).squeeze(-1)  # [B, L]
        scores = scores.masked_fill(mask == 0, self.mask_fill_num)
        weights = F.softmax(scores, dim=-1)
        weights = self.dropout(weights)

        # Pool from the projected features (not original lstm_output)
        masked_proj = proj * mask.unsqueeze(-1)
        context = torch.bmm(weights.unsqueeze(1), masked_proj).squeeze(1)
        return context


class MultiHeadAttention(nn.Module):
    def __init__(self, hidden_dim, num_heads=model_cfg.NUM_HEADS):
        super().__init__()
        head_dim = hidden_dim // num_heads
        self.heads = nn.ModuleList(
            [AttentionHead(hidden_dim, head_dim) for _ in range(num_heads)]
        )
        self.out_linear = nn.Linear(head_dim * num_heads, hidden_dim)

    def forward(self, hidden_state, mask):
        x = torch.cat([h(hidden_state, mask) for h in self.heads], dim=-1)
        x = self.out_linear(x)
        return x


class QuoraSiameseClassifier(nn.Module):
    def __init__(self, vocab_size, config=model_cfg, embedding=None, stop_mask=None):
        super().__init__()
        self.config = config
        self.embedding = nn.Embedding(vocab_size, config.EMB_DIM)
        self.emb_norm = nn.LayerNorm(config.EMB_DIM)
        self.emb_dropout = nn.Dropout(config.EMB_DP)
        if stop_mask is not None:
            self.register_buffer("stop_mask", stop_mask)
        else:
            self.stop_mask = None
        if embedding is not None:
            print("Glove copied in Embedding Layer...")
            self.embedding.weight.data.copy_(embedding)
            self.embedding.weight.requires_grad = not config.FREEZE_TOKEN_EMBEDDING

        self.LSTM = nn.LSTM(
            input_size=config.EMB_DIM,
            hidden_size=config.HIDDEN_DIM,
            bidirectional=config.BIDIRECTIONAL,
            num_layers=config.NUM_LAYERS,
            dropout=config.DROPOUT if config.NUM_LAYERS > 1 else 0.0,
            batch_first=True,
        )
        self.lstm_norm = nn.LayerNorm(config.LSTM_OUT)
        self.attention = MultiHeadAttention(config.LSTM_OUT)
        if config.ATTENTION_PROJECTION:
            self.proj = nn.Linear(config.LSTM_OUT, config.PROJECT_DIM)
        else:
            self.proj = nn.Identity()

        self.attn_norm = nn.LayerNorm(config.LSTM_OUT)
        self.fc_dims = self._build_fc_layers(
            input_dim=config.INPUT_FC_DIM,
            fc_dims=config.FC_DIMS,
            dropout=config.FC_DP,
        )

    def _build_fc_layers(self, input_dim, fc_dims, dropout):
        layers = []
        for dim in fc_dims:
            layers += [nn.Linear(input_dim, dim), nn.GELU(), nn.Dropout(dropout)]
            input_dim = dim
        layers.append(nn.Linear(input_dim, 1))  # final logit projection
        return nn.Sequential(*layers)

    def _create_mask(self, question):
        return (question != 0).float()

    def _encode(self, question):
        emb = self.embedding(question)
        if self.config.LAYER_NORM_EMB:
            emb = self.emb_norm(emb)
        emb = self.emb_dropout(emb)
        mask = self._create_mask(question)
        if self.stop_mask is not None:
            token_stop_mask = self.stop_mask[question]
            mask = mask * token_stop_mask.float()
        out, _ = self.LSTM(emb)
        if self.config.LAYER_NORM_LSTM:
            out = self.lstm_norm(out)
        ctx = self.attention(out, mask)
        if self.config.LAYER_NORM_ATTENTION:
            ctx = self.attn_norm(ctx)
        return ctx

    def forward(self, q1, q2):
        h1 = self._encode(q1)
        h2 = self._encode(q2)
        h1, h2 = self.proj(h1), self.proj(h2)
        cosine_sim = F.cosine_similarity(h1, h2).unsqueeze(-1)
        feat = torch.cat([h1, h2, abs(h1 - h2), h1 * h2, cosine_sim], dim=1)
        logits = self.fc_dims(feat)
        return logits.squeeze(-1)


class BCEWithLabelSmoothing(nn.Module):
    def __init__(self, epsilon, reduction="mean"):
        super().__init__()
        self.epsilon = epsilon
        self.criterion = nn.BCEWithLogitsLoss(reduction=reduction)

    def forward(self, logits, labels):
        labels = labels.float()
        labels = labels * (1 - self.epsilon) + (1 - labels) * self.epsilon
        return self.criterion(logits, labels)


class EarlyStopping:
    def __init__(self, patience=5, mode="min", min_delta=0.0):
        self.patience = patience
        self.mode = mode
        self.min_delta = min_delta

        self.should_stop = False
        self.best_score = None
        self.counter = 0

    def step(self, current_score):
        if self.best_score is None:
            self.best_score = current_score
            return True

        if self.mode == "min":
            improvement = self.best_score - current_score > self.min_delta
        else:
            improvement = current_score - self.best_score > self.min_delta

        if improvement:
            self.best_score = current_score
            self.counter = 0
            return True
        else:
            self.counter += 1
            if self.counter >= self.patience:
                self.should_stop = True
            return False


class TrainingHistory:
    def __init__(self):
        self.history = defaultdict(list)

    def update(self, train_loss, val_loss, train_metrics, val_metrics, optimizer):
        self.history["train_loss"].append(train_loss)
        self.history["val_loss"].append(val_loss)
        for k_t, v_t in train_metrics.items():
            self.history[f"train_{k_t.lower()}"].append(v_t)
        for k_v, v_v in val_metrics.items():
            self.history[f"val_{k_v.lower()}"].append(v_v)
        self.history["learning_rate"].append(optimizer.param_groups[0]["lr"])


class MLflowTracker:
    def __init__(
        self, project_name, run_type, config_dict, mlflow_dir, tracking_uri=None
    ):
        model_type = config_dict["model"]["model_type"]
        attention_type = config_dict["model"]["attention_type"]
        self.experiment_name = f"{project_name}/{model_type}"
        self.attn_type = attention_type
        self.model_type = model_type
        self.base_run_name = f"{model_type}-{attention_type}"
        self.run_type = run_type
        self.config_dict = config_dict
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
        else:
            mlflow.set_tracking_uri("http://localhost:5000")

        self.experiment = mlflow.get_experiment_by_name(self.experiment_name)
        artifact_dir = (mlflow_dir / project_name / model_type).as_uri()
        if self.experiment is None:
            mlflow.create_experiment(
                name=self.experiment_name, artifact_location=artifact_dir
            )
            print(f">>> Created new experiment: {self.experiment_name}")
        else:
            print(f">>> Using existing experiment: {self.experiment_name}")

        mlflow.set_experiment(self.experiment_name)
        self.run_name = self._generated_versioned_run_name()
        print(f">>> Run Name: {self.run_name}")

    def _generated_versioned_run_name(self):
        base = self.base_run_name
        experiment = self.experiment
        if self.experiment is None:
            return f"{base}-v1"

        runs_df = mlflow.search_runs(
            experiment_ids=[experiment.experiment_id],
            filter_string="tags.status = 'completed'",
        )
        if runs_df.empty:
            return f"{base}-v1"

        prefix = f"{base}-v"
        mask = runs_df["tags.mlflow.runName"].str.startswith(prefix, na=False)
        matching = runs_df.loc[mask, "tags.mlflow.runName"]

        if matching.empty:
            return f"{base}-v1"

        versions = []
        for name in matching:
            try:
                version_str = name.split("-v")[-1]
                versions.append(int(version_str))
            except (ValueError, IndexError):
                continue
        next_version = max(versions) + 1 if versions else 1
        return f"{base}-v{next_version}"

    def start_run(self):
        self.run = mlflow.start_run(run_name=self.run_name)
        self.run_id = self.run.info.run_id
        return self.run

    def log_param(self, param_name, param):
        mlflow.log_param(param_name, param)

    def log_params(self, params):
        mlflow.log_params(params)

    def log_metric(self, name, value, epoch):
        mlflow.log_metric(name, value, step=epoch)

    def log_config_params(self):
        for key, value in self.config_dict.items():
            if key not in ["system", "path"]:
                mlflow.log_params(value)

    def _log_losses(self, train_loss, val_loss, epoch):
        mlflow.log_metric("train_loss", train_loss, step=epoch)
        mlflow.log_metric("val_loss", val_loss, step=epoch)

    def _log_metrics(self, metrics_dict, epoch, prefix):
        for metric, value in metrics_dict.items():
            mlflow.log_metric(f"{prefix}_{metric.lower()}", value, step=epoch)

    def log_epoch(self, epoch, train_loss, val_loss, train_results, val_results, lr):
        self._log_losses(train_loss, val_loss, epoch)
        self._log_metrics(train_results, epoch, prefix="train")
        self._log_metrics(val_results, epoch, prefix="val")
        mlflow.log_metric("learning_rate", lr, step=epoch)

    def save_state_dict(self, state_dict, checkpoint_path):
        mlflow.pytorch.save_state_dict(state_dict, path=checkpoint_path)

    def load_state_dict(self, model, checkpoint_path):
        loaded_state_dict = mlflow.pytorch.load_state_dict(checkpoint_path)
        model.load_state_dict(loaded_state_dict)
        return model

    def log_best_model(self, model):
        mlflow_logger = logging.getLogger("mlflow.pytorch")
        original_level = mlflow_logger.level
        mlflow_logger.setLevel(logging.ERROR)
        mlflow.pytorch.log_model(
            model, name="best_models", registered_model_name=self.run_name
        )
        mlflow_logger.setLevel(original_level)

    def log_artifact(self, artifact_path):
        mlflow.log_artifact(artifact_path)

    def log_artifact_folder(self, artifact_folder):
        mlflow.log_artifacts(artifact_folder)

    def build_run_summary(
        self,
        best_threshold,
        training_metrics,
        calibrated_metrics,
        total_time,
        avg_time_per_epoch,
    ):
        summary = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "run_type": self.run_type,
            "model_type": self.model_type,
            "attention_type": self.attn_type,
            "run_id": self.run_id,
            "best_metrics_in_training": training_metrics,
            "best_threshold": best_threshold,
            "best_calibrated_metrics": calibrated_metrics,
            "total_training_time_in_min": total_time,
            "average_training_time_per_epoch": avg_time_per_epoch,
            "params": {},
        }
        for k, v in self.config_dict.items():
            if k not in ["system", "path"]:
                summary["params"][k] = v
        return summary

    def log_summary(self, summary, artifact_name="run_sammary.json"):
        mlflow.log_dict(summary, artifact_name)

    def log_history(self, history, artifact_name="training_history.json"):
        mlflow.log_dict(history, artifact_name)

    def set_final_tags(
        self, best_score, best_calib_score, best_threshold, total_training_time
    ):
        mlflow.set_tags(
            {
                "status": "completed",
                "model_type": self.model_type,
                "attention_type": self.attn_type,
                "best_training_score": best_score,
                "best_calibrated_score": best_calib_score,
                "best_threshold": best_threshold,
                "total_training_time_in_min": total_training_time,
            }
        )


class Trainer:
    def __init__(
        self,
        model,
        train_loader,
        val_loader,
        criterion,
        optimizer,
        device,
        history,
        mlflow_tracker,
        config=train_cfg,
        scaler=None,
    ):
        self.model = model
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.device = device
        self.history = history
        self.config = config
        self.criterion = criterion
        self.criterion_eval = nn.BCEWithLogitsLoss()
        self.optimizer = optimizer
        self.tracker = mlflow_tracker
        self.scaler = scaler

        self.early_stopper = EarlyStopping(
            patience=config.EARLY_STOP_PATIENCE,
            mode=config.EARLY_STOP_MODE,
            min_delta=config.EARLY_STOP_MIN_DELTA,
        )
        self.scheduler = self._create_scheduler(config.SCHEDULER_TYPE)

        threshold = config.METRICS_THRESHOLD
        self.best_threshold = threshold
        metrics_cls = [BinaryAccuracy, BinaryPrecision, BinaryRecall, BinaryF1Score]
        self.train_metrics = {
            m.__name__.replace("Binary", ""): m(threshold).to(device)
            for m in metrics_cls
        }
        self.train_metrics["AUROC"] = AUROC(task="binary").to(device)
        self.train_metrics["AveragePrecision"] = AveragePrecision(task="binary").to(
            device
        )
        self.val_metrics = {
            m.__name__.replace("Binary", ""): m(threshold).to(device)
            for m in metrics_cls
        }
        self.val_metrics["AUROC"] = AUROC(task="binary").to(device)
        self.val_metrics["AveragePrecision"] = AveragePrecision(task="binary").to(
            device
        )
        self.pr_curve = PrecisionRecallCurve(task="binary").to(device)

        self.best_checkpoint_score = (
            float("-inf") if config.CHECKPOINT_MODE == "max" else float("inf")
        )
        self.checkpoint_mode = config.CHECKPOINT_MODE

        self.train_start = Event(enable_timing=True)
        self.train_end = Event(enable_timing=True)
        self.epoch_start = Event(enable_timing=True)
        self.epoch_end = Event(enable_timing=True)
        self.epoch_durations = []
        self.current_epoch = 0

    def _create_scheduler(self, scheduler_type):
        if scheduler_type == "CosineAnnealing":
            return CosineAnnealingLR(
                optimizer=self.optimizer,
                T_max=self.config.EPOCHS,
                eta_min=self.config.SCHEDULER_ETA_MIN,
            )
        elif scheduler_type == "ReduceLROnPlateau":
            return ReduceLROnPlateau(
                optimizer=self.optimizer,
                patience=self.config.SCHEDULER_PATIENCE,
                factor=self.config.SCHEDULER_FACTOR,
                mode=self.config.SCHEDULER_MODE,
                min_lr=self.config.SCHEDULER_MIN_LR,
                threshold=self.config.SCHEDULER_THRESHOLD,
                threshold_mode=self.config.SCHEDULER_THRESHOLD_MODE,
            )
        elif scheduler_type == "OneCycleLR":
            return OneCycleLR(
                optimizer=self.optimizer,
                max_lr=self.config.LEARNING_RATE,
                epochs=self.config.EPOCHS,
                steps_per_epoch=len(self.train_loader),
                pct_start=self.config.SCHEDULER_PCT_START,
                div_factor=self.config.SCHEDULER_DIV_FACTOR,
                final_div_factor=self.config.SCHEDULER_FINAL_DIV_FACTOR,
            )
        elif scheduler_type == "CosineAnnealingWarmRestarts":
            return CosineAnnealingWarmRestarts(
                optimizer=self.optimizer,
                T_0=self.config.SCHEDULER_T_0,
                T_mult=self.config.SCHEDULER_T_MULT,
                eta_min=self.config.SCHEDULER_ETA_MIN,
            )
        elif scheduler_type in (None, "none"):
            print("Warning: No scheduler")
            return None
        else:
            raise ValueError(f"Unknown scheduler: {scheduler_type}")

    def _check_scheduler(self, scheduler_value):
        if self.scheduler:
            if isinstance(self.scheduler, ReduceLROnPlateau):
                old_lr = self.optimizer.param_groups[0]["lr"]
                self.scheduler.step(scheduler_value)
                new_lr = self.optimizer.param_groups[0]["lr"]
                if new_lr < old_lr:
                    print(f">>> LR reduced: {old_lr:.6f} -> {new_lr:.6f}")
            else:
                self.scheduler.step()

    def _unfreeze_embedding(self):
        self.model.embedding.weight.requires_grad = True
        print(">>> Embedding unfrozen (LR unchanged)")

    def _reset_metrics(self, metrics_dict):
        for metric in metrics_dict.values():
            metric.reset()

    def _update_metrics(self, metrics_dict, probs, labels):
        for metric in metrics_dict.values():
            metric.update(probs, labels)

    def _update_threshold(self, metrics_dict):
        for metric in metrics_dict.values():
            if hasattr(metric, "threshold"):
                metric.threshold = self.best_threshold

    def _compute_metrics(self, metrics_dict):
        return {k: m.compute().item() for k, m in metrics_dict.items()}

    def _get_metric_value(self, metric_name, val_loss, val_results):
        if metric_name == "loss":
            return val_loss
        else:
            return val_results[metric_name]

    def _is_checkpoint_better(self, current_value: float) -> bool:
        if self.checkpoint_mode == "max":
            return current_value > self.best_checkpoint_score
        else:
            return current_value < self.best_checkpoint_score

    def _backprop_with_scaler(self, q1, q2, labels):
        device_type = "cuda" if "cuda" in str(self.device) else "cpu"
        with autocast(enabled=self.scaler is not None, device_type=device_type):
            logits = self.model(q1, q2)
            loss = self.criterion(logits, labels)
        if self.scaler is not None:
            self.scaler.scale(loss).backward()

            if self.config.CLIP_NORM is not None and self.config.CLIP_NORM > 0:
                self.scaler.unscale_(self.optimizer)
                clip_grad_norm_(self.model.parameters(), self.config.CLIP_NORM)
            else:
                self.scaler.unscale_(self.optimizer)

            self.scaler.step(self.optimizer)
            self.scaler.update()
        else:
            loss.backward()
            if self.config.CLIP_NORM is not None and self.config.CLIP_NORM > 0:
                clip_grad_norm_(self.model.parameters(), self.config.CLIP_NORM)
            self.optimizer.step()

        return loss, logits

    def train_one_epoch(self):
        self.model.train()
        self._update_threshold(self.train_metrics)
        self._reset_metrics(self.train_metrics)
        total_loss = 0.0

        for batch in tqdm(self.train_loader, desc="Train", leave=True):
            q1 = batch["q1"].to(self.device)
            q2 = batch["q2"].to(self.device)
            labels = batch["label"].to(self.device).long()

            self.optimizer.zero_grad()
            loss, logits = self._backprop_with_scaler(q1, q2, labels)
            total_loss += loss.item() * q1.size(0)

            probs = torch.sigmoid(logits)
            self._update_metrics(self.train_metrics, probs, labels)

        total_loss /= len(self.train_loader.dataset)
        results = self._compute_metrics(self.train_metrics)
        return total_loss, results

    @torch.no_grad()
    def evaluate(self, use_optimal_threshold=True):
        self.model.eval()
        total_loss = 0.0
        all_logits, all_labels = [], []

        for batch in tqdm(self.val_loader, desc="Validation", leave=True):
            q1 = batch["q1"].to(self.device)
            q2 = batch["q2"].to(self.device)
            labels = batch["label"].to(self.device).long()

            logits = self.model(q1, q2)
            loss = self.criterion_eval(logits, labels.float())
            total_loss += loss.item() * q1.size(0)

            all_logits.append(logits)
            all_labels.append(labels)

        total_loss /= len(self.val_loader.dataset)

        all_logits = torch.cat(all_logits)
        all_labels = torch.cat(all_labels)
        all_probs = torch.sigmoid(all_logits)

        if use_optimal_threshold:
            self.pr_curve.reset()
            all_labels = all_labels.long()
            self.pr_curve.update(all_probs, all_labels)
            precision, recall, thresholds = self.pr_curve.compute()
            if thresholds.numel() > 0:
                f1_scores = 2 * precision * recall / (precision + recall + 1e-8)
                best_idx = torch.argmax(f1_scores)
                self.best_threshold = thresholds[best_idx].item()
            else:
                self.best_threshold = self.config.METRICS_THRESHOLD
        else:
            self.best_threshold = self.config.METRICS_THRESHOLD

        self._update_threshold(self.val_metrics)
        self._reset_metrics(self.val_metrics)
        self._update_metrics(self.val_metrics, all_probs, all_labels)
        results = self._compute_metrics(self.val_metrics)

        return total_loss, results

    def log_one_epoch(
        self, train_loss, train_results, val_loss, val_results, best_thresh, lr
    ):
        print(f"Training Results:\n\tLoss --> {train_loss:.4f}")
        train_string = ""
        val_string = ""
        for k, v in train_results.items():
            train_string += f"{k} --> {v:.4f} | "
        print(f"\t{train_string}")
        print(f"\tLearning Rate --> {lr:.6f}\n")
        print(f"Validation Results:\n\tLoss --> {val_loss:.4f}")
        print(f"\tOptimal Best Threhsold --> {best_thresh}")
        for k, v in val_results.items():
            val_string += f"{k} --> {v:.4f} | "
        print(f"\t{val_string}")

    @torch.no_grad()
    def find_optimal_threshold(self):
        self.model.eval()
        _, results = self.evaluate(use_optimal_threshold=True)
        best_threshold = self.best_threshold

        print(f">>> Optimal threshold: {best_threshold:.4f}")
        print(
            f">>> At that threshold --> F1: {results['F1Score']:.4f}, "
            f"Precision: {results['Precision']:.4f}, Recall: {results['Recall']:.4f}"
        )
        return best_threshold, results

    def fit(self, num_epochs, config=path_cfg):
        self.train_start.record()

        print(">>> Training Started...")
        with self.tracker.start_run():
            self.tracker.log_config_params()
            self.tracker.log_artifact(config.VOCABS_PATH)
            self.tracker.log_artifact(config.LABEL_MAPPING_PATH)
            self.tracker.log_artifact(config.CONFIG_PATH)

            best_metrics = {}

            for epoch in range(num_epochs):
                self.current_epoch = epoch
                print(f"Epoch {epoch + 1}/{num_epochs}")
                self.epoch_start.record()
                torch.cuda.synchronize()

                if (
                    self.config.UNFREEZE_EPOCH is not None
                    and epoch == self.config.UNFREEZE_EPOCH
                ):
                    print(f">>> Embedding is unfrozen from epoch {epoch + 1}")
                    self._unfreeze_embedding()

                train_loss, train_results = self.train_one_epoch()
                val_loss, val_results = self.evaluate()

                early_stop_value = self._get_metric_value(
                    self.config.EARLY_STOP_METRIC, val_loss, val_results
                )
                scheduler_value = self._get_metric_value(
                    self.config.SCHEDULER_METRIC, val_loss, val_results
                )
                checkpoint_value = self._get_metric_value(
                    self.config.CHECKPOINT_METRIC, val_loss, val_results
                )

                self._check_scheduler(scheduler_value)

                self.history.update(
                    train_loss=train_loss,
                    val_loss=val_loss,
                    train_metrics=train_results,
                    val_metrics=val_results,
                    optimizer=self.optimizer,
                )

                lr = self.optimizer.param_groups[0]["lr"]
                self.log_one_epoch(
                    train_loss=train_loss,
                    train_results=train_results,
                    val_loss=val_loss,
                    val_results=val_results,
                    best_thresh=self.best_threshold,
                    lr=lr,
                )
                self.tracker.log_epoch(
                    epoch=epoch,
                    train_loss=train_loss,
                    val_loss=val_loss,
                    train_results=train_results,
                    val_results=val_results,
                    lr=lr,
                )
                self.tracker.log_metric("best_threshold", self.best_threshold, epoch)
                self.early_stopper.step(early_stop_value)

                if self._is_checkpoint_better(checkpoint_value):
                    self.best_checkpoint_score = checkpoint_value
                    best_metrics = val_results
                    self.tracker.save_state_dict(
                        self.model.state_dict(), config.CHECKPOINT_DIR
                    )
                    print(
                        f">>> Best model saved! "
                        f"({self.config.CHECKPOINT_METRIC} --> {checkpoint_value:.4f})"
                    )

                if self.early_stopper.should_stop:
                    print(f">>> Early stopping triggered at Epoch {epoch + 1}")
                    break

                self.epoch_end.record()
                torch.cuda.synchronize()

                epoch_duration = self.epoch_start.elapsed_time(self.epoch_end) / 1000
                self.epoch_durations.append(epoch_duration)
                print("=" * sys_cfg.NEXT_LINE_COUNTER)

            self.train_end.record()
            torch.cuda.synchronize()
            total_training_time = self.train_start.elapsed_time(self.train_end) / 1000
            avg_time_per_epoch = sum(self.epoch_durations) / len(self.epoch_durations)
            total_training_time_in_min = round(total_training_time / 60, 2)
            avg_time_per_epoch_in_min = round(avg_time_per_epoch / 60, 2)

            self.model = self.tracker.load_state_dict(self.model, config.CHECKPOINT_DIR)
            self.model.eval()
            final_best_threshold, calibrated_results = self.find_optimal_threshold()
            self.tracker.log_artifact_folder(config.CHECKPOINT_DIR)
            self.tracker.log_best_model(self.model)
            print(">>> The Best Model registered at MLflow successfully!")

            summary = self.tracker.build_run_summary(
                best_threshold=final_best_threshold,
                training_metrics=best_metrics,
                calibrated_metrics=calibrated_results,
                total_time=total_training_time_in_min,
                avg_time_per_epoch=avg_time_per_epoch_in_min,
            )
            self.tracker.log_param(
                f"best_training_{self.config.CHECKPOINT_METRIC}",
                self.best_checkpoint_score,
            )
            self.tracker.log_param(
                f"best_calibrated_{self.config.CHECKPOINT_METRIC}",
                calibrated_results[self.config.CHECKPOINT_METRIC],
            )
            self.tracker.log_param("best_threshold", final_best_threshold)
            self.tracker.log_params(calibrated_results)
            self.tracker.log_summary(summary)
            self.tracker.log_history(self.history)
            self.tracker.set_final_tags(
                best_score=self.best_checkpoint_score,
                best_calib_score=calibrated_results[self.config.CHECKPOINT_METRIC],
                best_threshold=final_best_threshold,
                total_training_time=total_training_time_in_min,
            )


def main():
    scaler = set_scaler(sys_cfg)
    seed_everything(sys_cfg.SEED, deterministic=sys_cfg.IS_DETERMINISTIC)
    print(f">>> Training on: {sys_cfg.DEVICE} with seed = {sys_cfg.SEED}")

    clean_artifact_directory(path_cfg.ARTIFACT_DIR)
    configs = configs_dict(path_cfg.CONFIG_PATH)

    df = pd.read_csv(path_cfg.TRAIN_CSV_PATH)
    preprocessor = QuoraPreproccesor(config=token_cfg)
    df = preprocessor.preprocess_df(df)

    train_df, val_df = train_test_split(
        df,
        random_state=sys_cfg.SEED,
        shuffle=True,
        stratify=df["is_duplicate"],
        train_size=train_cfg.TRAIN_TEST_SPLIT,
    )

    tokenizer = QuoraTokenizer(config=token_cfg)
    tokenizer.build_vocabs(train_df)
    stop_mask = tokenizer.stop_mask
    embedding = tokenizer.load_embedding(model_cfg.EMB_DIM, path_cfg.EMB_PATH)
    tokenizer.save(path_cfg.VOCABS_PATH)
    tokenizer.save_label_mapping(path_cfg.LABEL_MAPPING_PATH)

    train_dataset = QuoraDataset(train_df, tokenizer=tokenizer)
    val_dataset = QuoraDataset(val_df, tokenizer=tokenizer)

    train_dataloader = DataLoader(
        train_dataset,
        batch_size=loader_cfg.BATCH_SIZE,
        shuffle=True,
        num_workers=loader_cfg.NUM_WORKERS,
        pin_memory=loader_cfg.IS_PIN_MEMORY,
    )
    val_dataloader = DataLoader(
        val_dataset,
        batch_size=loader_cfg.BATCH_SIZE,
        shuffle=False,
        num_workers=loader_cfg.NUM_WORKERS,
        pin_memory=loader_cfg.IS_PIN_MEMORY,
    )

    model = QuoraSiameseClassifier(
        vocab_size=token_cfg.VOCAB_SIZE,
        config=model_cfg,
        embedding=embedding,
        stop_mask=stop_mask,
    ).to(sys_cfg.DEVICE)
    print(model)
    print(f"Total Number of Parameters: {sum(p.numel() for p in model.parameters())}")

    mlflow_tracker = MLflowTracker(
        project_name="Quora-Question-Pairs",
        run_type="exploring-best-architecture",
        config_dict=configs,
        mlflow_dir=path_cfg.MLFLOW_DIR,
        tracking_uri=sys_cfg.MLFLOW_TRACKING_URI,
    )
    history = TrainingHistory()
    criterion = BCEWithLabelSmoothing(epsilon=model_cfg.LABEL_SMOOTHING)
    optimizer = torch.optim.AdamW(
        [
            {
                "params": [
                    p for n, p in model.named_parameters() if "embedding" not in n
                ],
                "lr": train_cfg.LEARNING_RATE,
            },
            {
                "params": [model.embedding.weight],
                "lr": train_cfg.LEARNING_RATE / 10,
                "requires_grad": False,
            },
        ],
        weight_decay=train_cfg.WEIGHT_DECAY,
    )

    trainer = Trainer(
        model=model,
        train_loader=train_dataloader,
        val_loader=val_dataloader,
        criterion=criterion,
        optimizer=optimizer,
        device=sys_cfg.DEVICE,
        history=history,
        config=train_cfg,
        mlflow_tracker=mlflow_tracker,
        scaler=scaler,
    )
    trainer.fit(num_epochs=train_cfg.EPOCHS, config=path_cfg)


if __name__ == "__main__":
    main()
