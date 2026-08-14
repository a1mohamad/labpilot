# Attentive Siamese BiLSTM Encoders for Duplicate Question Detection

*Reference description of the method. Side A of the LabPilot sample pair.*

## Abstract

We present a siamese recurrent architecture for deciding whether two natural
language questions ask the same thing. Each question is encoded independently by
a shared bidirectional LSTM. A multi-head additive attention layer pools the
recurrent hidden states into a single sentence vector. The two sentence vectors
are combined with element-wise interaction features and classified by a small
feed-forward network. On the Quora Question Pairs benchmark the model reaches
0.878 accuracy and 0.851 F1 on the held-out test split, using only 100
dimensional pre-trained word vectors and no transformer components.

## 1. Introduction

Duplicate question detection is a sentence pair classification problem. Given
two questions, the model must output the probability that they are semantically
equivalent. The task is harder than it appears because the two questions often
share almost every content word and differ only in a function word, a negation,
or a single argument.

Our goal in this work is a strong non-transformer baseline. We deliberately
restrict the model to a recurrent encoder and frozen 100 dimensional word
vectors, so that the contribution of the attention mechanism and of the pair
interaction features can be measured without the confound of large scale
pre-training.

## 2. Related Work

Siamese recurrent encoders for sentence similarity were popularised by manhattan
LSTM style architectures, which encode both sentences with one shared network and
compare the two final hidden states. Later work replaced the final hidden state
with an attention-weighted pooling over all timesteps, and replaced the distance
based comparison with a learned classifier over interaction features. Our model
follows that second line.

## 3. Problem Formulation

Let a training example be a triple $(q^{(1)}, q^{(2)}, y)$ where $q^{(1)}$ and
$q^{(2)}$ are token sequences and $y \in \{0, 1\}$ indicates that the two
questions are duplicates. We learn a shared encoder $f_\theta$ and a classifier
$g_\phi$, and model

$$
P(y = 1 \mid q^{(1)}, q^{(2)}) = \sigma\big(g_\phi(f_\theta(q^{(1)}), f_\theta(q^{(2)}))\big).
$$

The encoder is shared between the two sides. Sharing is what makes the
architecture siamese, and it halves the parameter count of the encoder.

## 4. Method

### 4.1 Input representation and tokenization

Questions are lowercased before tokenization. Punctuation is separated from
adjacent words so that it becomes its own token. Tokenization is whitespace
based after this normalization step.

The vocabulary is built from the training split only, and is capped at the
20,000 most frequent tokens. Two reserved symbols are added: a padding symbol at
index 0 and an unknown symbol at index 1. Tokens outside the vocabulary are
mapped to the unknown symbol.

Every question is truncated or padded to a fixed length of 50 tokens. Padding is
applied on the right.

Word vectors are initialised from 100 dimensional GloVe vectors trained on the
6B token corpus. Tokens that have no GloVe vector are initialised from a normal
distribution with zero mean and standard deviation 0.05. The padding vector is
initialised to zero and is never updated.

### 4.2 Sentence encoder

The encoder is a bidirectional LSTM with 2 layers and 384 hidden units per
direction, so the concatenated output width is 768. Dropout of 0.35 is applied
between the two recurrent layers.

The encoder runs over the full padded sequence. Positions that correspond to
padding are excluded from pooling by a binary mask. **The mask excludes padding
positions and nothing else.** Every real token of the question, including
function words, punctuation and unknown tokens, remains available to the
attention layer.

### 4.3 Attention pooling

Pooling turns the variable length sequence of hidden states into one fixed
vector. We use additive attention in the style of Bahdanau, extended to multiple
heads.

Let $H = [h_1, \dots, h_L] \in \mathbb{R}^{L \times d}$ be the hidden states
produced by the encoder for a question of padded length $L$, with $d = 768$.
A single attention head first projects each hidden state into a subspace of
width $d_k = d / K$, where $K$ is the number of heads,

$$
u_i = \tanh(W h_i), \qquad W \in \mathbb{R}^{d_k \times d},
$$

then scores each position with a learned vector $v \in \mathbb{R}^{d_k}$,

$$
e_i = v^\top u_i .
$$

Masked positions receive a large negative score before the softmax, so that
their attention weight is numerically zero,

$$
\alpha_i = \frac{\exp(e_i)}{\sum_{j=1}^{L} \exp(e_j)} .
$$

The head then returns a weighted sum **of the encoder hidden states**,

$$
c = \sum_{i=1}^{L} \alpha_i \, h_i \in \mathbb{R}^{d} .
$$

This point matters and is easy to get wrong in an implementation. The projection
$W$ exists only to compute the scores. It must not be applied to the vectors
that are summed. Pooling the projected vectors $u_i$ instead of the hidden
states $h_i$ changes the output space of the attention layer from $d$ to $d_k$,
discards the information that the projection removed, and makes the pooled
representation depend on the scoring parameters. In our ablations that variant
costs 1.4 F1 points, which is larger than the gain from multiple heads.

We use $K = 4$ heads. The head outputs are concatenated and passed through a
final linear layer of width 768, which returns the sentence vector to the width
of the encoder output. No layer normalization is applied inside the attention
block. Attention dropout is not used.

The attention weights are also useful for inspection. Because every non-padding
token is a candidate, the weights can be read directly as an explanation of
which words the model considered decisive for a given pair.

### 4.4 Pair interaction and classifier

Let $u$ and $v$ be the two sentence vectors produced by the shared encoder. We
build the interaction vector by concatenating four blocks,

$$
r = [\, u \,;\, v \,;\, |u - v| \,;\, u \odot v \,] \in \mathbb{R}^{4d},
$$

where $\odot$ is the element-wise product. The absolute difference captures
disagreement between the two encodings and the element-wise product captures
agreement. Both are needed: removing either one costs more than one F1 point.

The interaction vector is classified by a feed-forward network with two hidden
layers of width 1024 and 256. Each hidden layer uses a GELU activation followed
by dropout with probability 0.4. The output layer is a single logit.

### 4.5 Training objective

We optimise binary cross entropy on the logit. The Quora training set is
imbalanced, with 36.9 percent positive pairs, so the positive class is weighted
by the ratio of negative to positive examples computed on the training split,

$$
w_{+} = \frac{N_{-}}{N_{+}} \approx 1.71 .
$$

Label smoothing with $\varepsilon = 0.1$ is applied to the targets before the
loss is computed, so a positive target becomes 0.9 and a negative target becomes
0.1. Smoothing reduces the confidence of the logits and improved calibration in
our experiments without changing accuracy.

## 5. Experimental Setup

### 5.1 Dataset and splits

We use the Quora Question Pairs corpus of 404,290 labelled pairs. Rows in which
either question is empty after normalization are removed.

The corpus is divided into three parts. 80 percent is used for training, 10
percent is held out as a development set, and the remaining 10 percent is held
out as a test set. The split is stratified on the label and is drawn once with a
fixed seed. The test split is used only to produce the numbers in Section 6 and
is never used for model selection, early stopping, or threshold tuning.

### 5.2 Optimization

We train with AdamW at a base learning rate of 3e-4 and a weight decay of 0.01.
The batch size is 128.

The learning rate follows a linear warmup over the first 2 epochs, from zero to
the base rate, and then a cosine decay to a floor of 1e-6 over the remaining
epochs. Warmup matters here because the classifier head is randomly initialised
while the embeddings are pre-trained, and a large step in the first few hundred
updates distorts the pre-trained space.

Gradients are clipped to a global norm of 1.0 before each optimizer step.

Word embeddings are frozen for the first 2 epochs and unfrozen from epoch 3
onward. After unfreezing, the embedding parameters are placed in their own
optimizer group with a learning rate of one tenth the base rate.

We train for at most 50 epochs and stop early when the development loss has not
improved by more than 1e-4 for 5 consecutive epochs.

### 5.3 Reproducibility

Every reported number is the mean of 3 runs that differ only in the random seed.
Each run fixes the seed of Python, NumPy and PyTorch, and enables deterministic
kernels. We report the standard deviation across seeds alongside the mean.

### 5.4 Evaluation protocol

We report accuracy, precision, recall, F1 and the area under the ROC curve.

The decision threshold is not fixed at 0.5. It is selected once, at the end of
training, as the value that maximises F1 on the **development** set. That single
threshold is then applied unchanged to the test set. Selecting the threshold on
the same data used to report the metric inflates F1 by roughly 1.5 points in our
experience and makes the number incomparable with other work.

## 6. Results

| Model | Accuracy | Precision | Recall | F1 | AUROC |
|---|---|---|---|---|---|
| BiLSTM, last hidden state | 0.842 | 0.795 | 0.802 | 0.798 | 0.908 |
| BiLSTM, mean pooling | 0.855 | 0.812 | 0.821 | 0.816 | 0.921 |
| BiLSTM, single-head attention | 0.869 | 0.831 | 0.845 | 0.838 | 0.933 |
| **BiLSTM, 4-head attention (ours)** | **0.878** | **0.842** | **0.861** | **0.851** | **0.941** |

All numbers are on the held-out test split, at the threshold selected on the
development split. The standard deviation across the 3 seeds is at most 0.004
for every column.

Training F1 at the final epoch is 0.872, so the gap between training and test F1
is 2.1 points. We take this as evidence that the dropout rates of Section 4 are
sufficient for this model size, and we did not need to add further
regularization. A gap much larger than this indicates that the encoder is
memorising pairs rather than learning the similarity function, and it usually
appears once the embedding matrix is made trainable.

## 7. Ablations

| Variant | F1 | Change |
|---|---|---|
| Full model | 0.851 | — |
| Pool projected features instead of hidden states | 0.837 | −1.4 |
| Without positive class weighting | 0.832 | −1.9 |
| Without warmup | 0.843 | −0.8 |
| Without label smoothing | 0.849 | −0.2 |
| Remove $\lvert u - v \rvert$ from the interaction vector | 0.836 | −1.5 |
| Remove $u \odot v$ from the interaction vector | 0.839 | −1.2 |
| Single head instead of 4 | 0.829 | −2.2 |
| Mask stopwords out of the attention | 0.810 | −4.1 |

The last row deserves comment. Removing function words from the attention mask
is a tempting simplification, because stopwords are frequent and carry little
topical meaning. On this task it is the single most damaging change we tried.
Duplicate detection turns on exactly those words: *how* against *why*, *is*
against *is not*, *from* against *to*. A pair that differs only by a negation
becomes indistinguishable once the negation cannot be attended to.

## 8. Limitations

The encoder is limited to 50 tokens, which truncates roughly 2 percent of
questions. The frozen 100 dimensional vectors limit the ceiling of the model;
larger vectors help, but the gain is smaller than the gain from attention
pooling. Finally, the corpus labels are known to be noisy, and we did not
attempt any label cleaning.
