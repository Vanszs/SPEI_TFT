import torch

from src.models.tft import load_tft_checkpoint


def load_model(checkpoint_path):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = load_tft_checkpoint(checkpoint_path, map_location=device)
    model.to(device)
    model.eval()
    return model

def calculate_metrics(actuals, predictions):
    """
    Calculate RMSE and MAE.
    predictions: Tensor of shape (batch, horizons, quantiles)
    QuantileLoss quantiles: [0.1, 0.5, 0.9]
    P50 (median) is at index 1.
    """
    p50_pred = predictions[:, :, 1]

    mse = torch.mean((actuals - p50_pred) ** 2)
    rmse = torch.sqrt(mse)
    mae = torch.mean(torch.abs(actuals - p50_pred))

    return {
        "RMSE": rmse.item(),
        "MAE": mae.item()
    }
