"""
SilentVoice — Sign Language Recognition Model (V4).

Architecture:
  Input(63/126) → Linear → LayerNorm → GELU
       → BiLSTM (residual)
       → PositionalEncoding
       → TransformerEncoder (4 layers)
       → MeanPool
       → Per-language classifier head

Supports:
  - Single hand (63 dims) or two hands (126 dims)
  - Separate classifier heads per language (ASL/ISL/TSL)
  - Template-based recognition fallback
"""

import math
from typing import Optional

import torch
import torch.nn as nn


class PositionalEncoding(nn.Module):
    def __init__(self, d_model: int, max_len: int = 512, dropout: float = 0.1):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)
        self.register_buffer("pe", pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.pe[:, :x.size(1)]
        return self.dropout(x)


class SignLanguageTransformer(nn.Module):
    """
    Per-language sign recognition model.

    Each language gets its own classifier head so ASL/ISL/TSL
    don't interfere with each other.
    """

    def __init__(
        self,
        input_dim: int = 63,
        d_model: int = 128,
        nhead: int = 4,
        num_layers: int = 3,
        dim_feedforward: int = 256,
        dropout: float = 0.15,
        vocab_size: int = 100,
        max_seq_len: int = 120,
        use_bilstm: bool = True,
        lstm_layers: int = 2,
        ctc_head: bool = False,
        # Per-language vocab sizes
        lang_vocab: Optional[dict] = None,
    ):
        super().__init__()
        self.use_bilstm = use_bilstm
        self.input_dim = input_dim
        self.d_model = d_model

        # Input projection
        self.input_projection = nn.Sequential(
            nn.Linear(input_dim, d_model),
            nn.LayerNorm(d_model),
            nn.GELU(),
            nn.Dropout(dropout),
        )

        # BiLSTM for temporal features
        if use_bilstm:
            self.bilstm = nn.LSTM(
                input_size=d_model,
                hidden_size=d_model // 2,
                num_layers=lstm_layers,
                batch_first=True,
                bidirectional=True,
                dropout=dropout if lstm_layers > 1 else 0,
            )
            self.lstm_norm = nn.LayerNorm(d_model)

        self.pos_encoder = PositionalEncoding(d_model, max_len=max_seq_len, dropout=dropout)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        # Shared feature extractor output
        self.feature_norm = nn.LayerNorm(d_model)

        # Per-language classifier heads
        if lang_vocab:
            self.lang_classifiers = nn.ModuleDict()
            for lang, size in lang_vocab.items():
                self.lang_classifiers[lang] = nn.Sequential(
                    nn.Linear(d_model, dim_feedforward),
                    nn.GELU(),
                    nn.Dropout(dropout),
                    nn.Linear(dim_feedforward, size),
                )
            self.classifier = None
        else:
            # Fallback: single classifier
            self.lang_classifiers = None
            self.classifier = nn.Sequential(
                nn.LayerNorm(d_model),
                nn.Linear(d_model, dim_feedforward),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(dim_feedforward, vocab_size),
            )

        # CTC head (optional)
        self.ctc_head = None
        if ctc_head:
            self.ctc_head = nn.Linear(d_model, vocab_size + 1)

    def extract_features(self, x: torch.Tensor, mask=None) -> torch.Tensor:
        """Extract temporal features from landmark sequence."""
        x = self.input_projection(x)

        if self.use_bilstm:
            lstm_out, _ = self.bilstm(x)
            x = self.lstm_norm(lstm_out + x)

        x = self.pos_encoder(x)
        x = self.transformer_encoder(x, src_key_padding_mask=mask)

        # Mean pool over time
        if mask is not None:
            mask_expanded = (~mask).unsqueeze(-1).float()
            x = (x * mask_expanded).sum(dim=1) / mask_expanded.sum(dim=1).clamp(min=1)
        else:
            x = x.mean(dim=1)

        return self.feature_norm(x)

    def forward(
        self,
        x: torch.Tensor,
        mask: Optional[torch.Tensor] = None,
        language: str = "ASL",
        return_ctc: bool = False,
    ) -> torch.Tensor:
        """
        Args:
            x: (batch, seq_len, input_dim)
            language: which language head to use
        Returns:
            logits: (batch, lang_vocab_size)
        """
        if return_ctc and self.ctc_head is not None:
            x = self.input_projection(x)
            if self.use_bilstm:
                lstm_out, _ = self.bilstm(x)
                x = self.lstm_norm(lstm_out + x)
            x = self.pos_encoder(x)
            x = self.transformer_encoder(x, src_key_padding_mask=mask)
            return self.ctc_head(x)

        features = self.extract_features(x, mask)

        if self.lang_classifiers and language in self.lang_classifiers:
            return self.lang_classifiers[language](features)
        elif self.classifier:
            return self.classifier(features)
        else:
            # Fallback to first available
            first_lang = list(self.lang_classifiers.keys())[0]
            return self.lang_classifiers[first_lang](features)

    def freeze_encoder(self):
        for module in [self.input_projection, self.pos_encoder, self.transformer_encoder]:
            for param in module.parameters():
                param.requires_grad = False
        if self.use_bilstm:
            for param in self.bilstm.parameters():
                param.requires_grad = False

    def unfreeze_encoder(self):
        for param in self.parameters():
            param.requires_grad = True
