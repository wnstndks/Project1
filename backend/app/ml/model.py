import torch
from torch import nn


class LSTMForecaster(nn.Module):
    """Stacked LSTM over a window of daily features -> cumulative returns for each horizon day."""

    def __init__(
        self, n_features: int, horizon: int, hidden: int = 64, layers: int = 2, dropout: float = 0.2
    ) -> None:
        super().__init__()
        self.lstm = nn.LSTM(
            n_features,
            hidden,
            num_layers=layers,
            batch_first=True,
            dropout=dropout if layers > 1 else 0,
        )
        self.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(hidden, horizon))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)
        return self.head(out[:, -1, :])
