# ReSort AI (Trash ML)

A small waste classifier that tells **glass**, **plastic**, **metal** and
**general waste** apart from a webcam image. It is built on TensorFlow and
MobileNetV2 transfer learning, and was started for the Hult Prize.

The repository also contains a **GPT + Claude coding workflow with human
approval** (`agent_controller/`), used to make reviewed changes to this code.

## What it does

- Trains a MobileNetV2 image classifier on a 4-class version of TrashNet,
  plus your own webcam photos.
- Evaluates a model on a fixed test set, with a confusion matrix and a list
  of the most confident mistakes.
- Classifies live webcam video and draws a box around the item.
- Includes a capture tool that saves webcam photos straight into the
  training folders.

## Classes

`general_waste`, `glass`, `metal`, `plastic`

The original TrashNet classes are mapped like this: cardboard, paper and
trash become `general_waste`; glass, metal and plastic stay as they are.

## Results so far

All numbers are on the same fixed test set (382 images, TrashNet style).
They do **not** measure webcam performance, because none of the webcam
photos are in the test set.

| Model | Training data | Test accuracy | Metal recall |
|---|---|---|---|
| v1 | TrashNet only | 84.6% | 76% |
| v2 | TrashNet + 502 webcam photos | 87.4% | 89% |
| v3 | v2 + fine-tuned last 30 layers | 87.2% | 92% |

Glass and metal are still confused with each other, so precision for those
two classes is the weak point. More varied glass and metal photos help more
than a bigger model did.

## Setup

Requires Python 3.11 and a webcam for the live tools.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

TensorFlow runs on the CPU on native Windows.

## Usage

### 1. Prepare the data

```powershell
python prepare_dataset.py
python split_dataset.py
```

`prepare_dataset.py` builds `dataset_4class/` and imports extra photos from
`dataset/extra_raw/<class>/`, skipping duplicates and staying under a 2 GB
total size cap. `split_dataset.py` makes the train, validation and test
splits and a `dataset_split/v2` set that adds the extra photos. The test
set is never changed, so models stay comparable.

### 2. Capture your own photos

```powershell
python capture_photos.py
```

Keys: `1`-`4` choose the class, `Space` saves a photo, `B` toggles burst
mode, `T` switches the box between fixed and following, `Q` quits. Photos
are saved to `dataset/extra_raw/<class>/`. Only the area inside the green
box is saved, the same area the model sees in `webcam.py`.

### 3. Train

```powershell
python train.py --data-dir dataset_split/v2 --model-path models/garbage_v2.keras
```

Options:

- `--data-dir` folder with `train/` and `validation/`.
- `--model-path` where to save the model. Training refuses to replace an
  existing file unless you pass `--overwrite`.
- `--fine-tune-layers N` after the normal training, also fine-tune the last
  N MobileNetV2 layers. The default `0` turns it off.

### 4. Evaluate

```powershell
python evaluate.py --model-path models/garbage_v2.keras
```

Prints accuracy, a classification report and a confusion matrix, then lists
the metal errors. It writes the metrics, a CSV of all mistakes and a
contact-sheet image of the most confident errors next to the model.

### 5. Live webcam

```powershell
python webcam.py --model-path models/garbage_v2.keras
```

Press `Q` to quit.

## Project layout

| Path | Purpose |
|---|---|
| `prepare_dataset.py`, `split_dataset.py` | Build the datasets and splits |
| `capture_photos.py` | Save webcam photos for training |
| `train.py` | Train and optionally fine-tune the model |
| `evaluate.py` | Test-set metrics and error analysis |
| `webcam.py` | Live classification |
| `agent_controller/` | GPT + Claude workflow with human approval |
| `tests/` | Unit tests for the workflow |
| `scripts/` | PowerShell helpers for the workflow |
| `dataset_4class/` | TrashNet images in the four classes |

Not stored in Git: `dataset/`, `dataset_split/`, `models/` and `.env`.

## GPT + Claude approval workflow

`agent_controller/` lets two AI agents propose changes while a human keeps
control:

1. GPT plans the investigation.
2. Claude inspects the project and proposes a unified diff.
3. You read the exact diff and type `APPROVE` to accept it.
4. The controller verifies the diff in a temporary worktree and applies
   exactly the approved diff.
5. Syntax checks and the unit tests run.
6. GPT reviews the result and reports problems.

The change is left uncommitted so you can review it and commit or undo it.
Proposals cannot touch the controller itself, `tests/`, `scripts/`, Git or
tool configuration, or `.env`. See `CLAUDE.md` for the rules.

Set `OPENAI_API_KEY` in a `.env` file (never commit it). An optional
`CLAUDE_MODEL` setting picks the Claude model. Run it with:

```powershell
python -m agent_controller.main
```

Run the tests with:

```powershell
python -B -m unittest discover -s tests -t . -v
```

The tests cover the controller only. They do not test the machine-learning
code.

## Data and licence notes

- The base images come from the TrashNet dataset (Yang and Thung), which is
  released under the MIT licence. Check the terms of any extra dataset you
  add.
- Webcam photos you capture stay local and are not committed.

## Known limitations

- Only about 2.5k base images, with clean backgrounds, so real-world
  accuracy depends heavily on your own photos.
- Glass and metal are the most confused pair.
- There is no separate webcam test set yet, so live accuracy is not
  measured.
