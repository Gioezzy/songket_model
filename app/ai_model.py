import torch
from PIL import Image
import os
import uuid
import gc

MODEL_PATH = "generator_scripted.pt"
OUTPUT_DIR = "static/images"

# Run inference on CPU
device = torch.device("cpu")
model = None

def load_model():
    global model
    if not os.path.exists(MODEL_PATH):
        print(f"Warning: Model file '{MODEL_PATH}' not found in backend directory!")
        return
        
    try:
        # Limit PyTorch CPU threads to significantly reduce RAM consumption on small servers
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        
        # Load TorchScript model
        model = torch.jit.load(MODEL_PATH, map_location=device)
        model.eval()
        print("AI model loaded successfully!")
    except Exception as e:
        print(f"Error loading model: {e}")

def generate_songket(category_idx: int, seed: int = None) -> tuple[str, int]:
    if model is None:
        raise Exception("generator_scripted.pt model not loaded.")
    
    if seed is not None:
        torch.manual_seed(seed)
    else:
        seed = torch.seed() & 0xFFFFFFFF
        torch.manual_seed(seed)
        
    # Use inference_mode (newer, faster, and uses less memory than no_grad)
    with torch.inference_mode():
        # Input shape for cDCGAN generator (noise tensor size 100)
        noise = torch.randn(1, 100, 1, 1, device=device)
        labels = torch.tensor([category_idx], dtype=torch.long, device=device)
        
        fake_image = model(noise, labels)
        
        # Denormalize output from [-1, 1] to [0, 1]
        fake_image = (fake_image + 1) / 2.0
        
        # Convert PyTorch Tensor to PIL Image
        ndarr = fake_image.squeeze(0).mul(255).add_(0.5).clamp_(0, 255).permute(1, 2, 0).to('cpu', torch.uint8).numpy()
        img = Image.fromarray(ndarr)
        
        # Super Resolution / Upscale to 512x512 using Lanczos resampling
        try:
            resampling_filter = Image.Resampling.LANCZOS
        except AttributeError:
            resampling_filter = Image.LANCZOS
        img_upscaled = img.resize((512, 512), resample=resampling_filter)
        
        # Save image as WebP format
        filename = f"mtf-{category_idx}-{seed}-{uuid.uuid4().hex[:6]}.webp"
        filepath = os.path.join(OUTPUT_DIR, filename)
        img_upscaled.save(filepath, format="WEBP", quality=85)
        
        # Explicitly clean up memory
        del noise
        del labels
        del fake_image
        gc.collect()
        
        return filename, seed
