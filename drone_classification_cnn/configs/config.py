"""
Patronus Acoustic - Configuration Module

All system parameters centralized for operational deployment.
"""
from pathlib import Path

class Config:
    """
    Central configuration for the acoustic threat detection system.

    Parameters are tuned for optimal drone signature detection
    """

    # ===========================================
    # PROJECT PATHS
    # ===========================================
    PROJECT_ROOT = Path(__file__).parent.parent
    DATA_DIR     = PROJECT_ROOT / "data"
    OUTPUT_DIR   = PROJECT_ROOT / "outputs"
    MODEL_DIR    = OUTPUT_DIR / "models"
    PLOTS_DIR    = OUTPUT_DIR / "plots"
    LOGS_DIR     = OUTPUT_DIR / "logs"

    # ===========================================
    # DATA Transfer
    # ===========================================
    BAUDRATE = 921600
    MAGIC    = 0x4C454D4C # Used to detect when new image is incoming

    # Q_SCALE and Q_OFFSET is used to send data efficiently from MCU to CNN pipeline
    Q_SCALE  = 1.50   # dequant: db = byte / Q_SCALE + Q_OFFSET
    Q_OFFSET = -100.0 # db value of byte 0

    # ===========================================
    # AUDIO PROCESSING PARAMETERS
    # ===========================================
    SAMPLE_RATE = 16000                       # Hz - Standard for audio ML
    DURATION    = 2.0                         # Seconds - Analysis window
    N_SAMPLES   = int(SAMPLE_RATE * DURATION) # Total samples per clip

    # Mel-Spectrogram Configuration
    FRAMES     = 61   # Number of frames per spectogram image
    N_FFT      = 1024 # FFT window size
    HOP_LENGTH = 512  # Stride between FFT windows
    N_MELS     = 128  # Number of Mel frequency bins
    F_MIN      = 100  # Minimum frequency (Hz)
    F_MAX      = 8000 # Maximum frequency (Hz) - Captures drone signatures

    # ===========================================
    # MODEL ARCHITECTURE
    # ===========================================
    MODEL_TYPE     = "custom_cnn" # Options: "custom_cnn", "resnet18"
    INPUT_CHANNELS = 1            # Mono audio -> single channel spectrogram
    NUM_CLASSES    = 2            # Binary: Drone (1) vs Safe (0)
    DROPOUT_RATE   = 0.5          # Regularization

    # ===========================================
    # TRAINING PARAMETERS
    # ===========================================
    BATCH_SIZE    = 32
    NUM_EPOCHS    = 50
    LEARNING_RATE = 1e-4
    WEIGHT_DECAY  = 1e-5 # L2 regularization

    # Early Stopping Configuration
    EARLY_STOPPING_PATIENCE  = 10
    EARLY_STOPPING_MIN_DELTA = 1e-4

    # Data Split Ratios
    TRAIN_RATIO = 0.7
    VAL_RATIO   = 0.15
    TEST_RATIO  = 0.15

    # ===========================================
    # DEFENSE-GRADE THRESHOLDS
    # ===========================================
    # In defense applications, missing a threat (False Negative) is catastrophic
    # We bias toward higher recall at the cost of some precision
    THREAT_CONFIDENCE_THRESHOLD = 0.4  # Lower threshold = fewer missed threats

    # Class Labels
    CLASS_NAMES  = ["Safe", "Threat"]
    SAFE_LABEL   = 0
    THREAT_LABEL = 1

    # ===========================================
    # UNPACKING PARQUET AUDIO DATASET
    # ===========================================
    DATA_INPUT_PATH   = DATA_DIR / "geronimobasso_drone-audio-detection-samples"
    DATA_OUTPUT_PATH  = DATA_DIR / "geronimobasso"
    DRONE_FOLDER      = "drone"
    BACKGROUND_FOLDER = "background"
    CLASS_NAMES       = {0: BACKGROUND_FOLDER, 1: DRONE_FOLDER} # Match with labels from downloaded dataset

    # ===========================================
    # SYSTEM CONFIGURATION
    # ===========================================
    RANDOM_SEED = 42
    NUM_WORKERS = 4    # DataLoader workers
    PIN_MEMORY  = True # GPU memory optimization

    @classmethod
    def create_directories(cls):
        """Create all necessary project directories."""
        directories = [
            cls.DATA_DIR,
            cls.OUTPUT_DIR,
            cls.MODEL_DIR,
            cls.PLOTS_DIR,
            cls.LOGS_DIR,
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_device(cls):
        """Get the best available compute device."""
        import torch
        if torch.cuda.is_available():
            return torch.device("cuda")
        elif torch.backends.mps.is_available():
            return torch.device("mps")  # Apple Silicon
        return torch.device("cpu")
