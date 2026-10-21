# Software
[Back to README](../README.md)

## Layout

```
docs/                     All relecant documents including md
drone_classification_cnn/ CNN pipeline (data_ingestion, train, model, detect)
NUCLEOH723ZG/             Current station firmware (STM32H723, CMake + CMSIS-DSP)
```

## NUCLEOH723ZG

#### Most important files

```
apps/        All applications get run from here
src/config/  Configuration values (mic_count, buffer_size)
src/drivers/ All drivers needed
src/dsp/     Handles pipeline from raw sound data to log-mel / DOA (SRP-PHAT)
src/types/   Contains audio type
tools/       Tools used to validate results (fft_viewer, log-mel_viewer)
x86_sandbox/ Code made to run on x86 for rapid testing and tweaking
```

#### Pipeline

| Step | Description |
|------|-------------|
| **ics5200** | Read raw sensor data from microphone, output buffer with 50% overlapping data |
| **spectrum** | Applies hann windowing and Fast Fourier Transform |
| **srp-phat** | Uses SRP-PAHT algorithm to detect DOA (Direction Of Arrival) |
| **log-mel** | Converts data to log-mel spectogram using filterbank weights from `mel-fbank.h` |
| **console** | Transfers the data over uart to external pc. |

## drone_classification_cnn

#### Most important files

```
configs/ Configuration values (data_processing, training_parameters, model, UART)
data/    Currently empty, need to call data_ingestion to get training data
outputs/ Outputs from training the model (logs, plots, model)
src/     Files needed for data_ingestion, preprocesing, training, detection
```


#### Pipeline

| Step | Description |
|------|-------------|
| **data_ingestion** | Collects data for training |
| **data_loader** | Preprocessing step turning .wav data to log-mel spectograms |
| **train** | Trains model with specifications set in `conifgs/config.py` |
| **detect** | Receives log-mel spectogram over UART which the model uses to predict drone / no drone |
