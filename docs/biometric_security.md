# Biometric Security Evaluation

## Security Pipeline

Live attendance uses this order:

1. Validate the submitted camera sequence and one dominant foreground face.
2. Run a random left or right head-turn challenge using MTCNN landmarks.
3. Verify primary-face continuity across the challenge.
4. Run FaceNet recognition only after active liveness passes.
5. Reuse the existing check-in/check-out use cases and attendance rules.

Failure at an active runtime security stage prevents attendance creation or
modification. Passive RGB presentation-attack detection (PAD) source code,
model metadata, capture tools, and calibration tools are retained for future
offline evaluation, but PAD is not called by the current live attendance
runtime. A missing PAD calibration therefore does not block attendance.

## Compatibility

The current active model identity remains:

```text
facenet-onnx-512d-haikalmumtaz-v1
```

Its embeddings use the legacy crop and are not silently mixed with aligned
embeddings. Alignment is implemented but remains disabled for `v1`. Enabling it
requires a model identity ending in `-aligned-v2`, an independent evaluation,
and explicit re-enrollment with 5 to 8 diverse, high-quality images.

## Private Sample Layout

Real biometric samples are local and ignored by Git:

```text
storage/evaluation/pad_samples/
    real/
      attempt_001/
      attempt_002/
    spoof/
      phone_static/
        attempt_001/
      printed_photo/
        attempt_001/
      tablet_static/
        attempt_001/
      replay_video/
        attempt_001/
```

Each PAD attempt should contain 8 to 12 frames captured by the deployment
camera. Do not copy the source photograph directly into this dataset. The
camera must observe the print or screen so the model can evaluate presentation
artifacts from the actual setup.

## Capture Attempts

Set the same camera configuration used by the kiosk:

```powershell
.\.venv\Scripts\Activate.ps1
$env:MOBILE_CAMERA_SOURCE="0"
$env:LIVE_CAMERA_FLIP="0"
$env:LIVE_CAMERA_ROTATE="0"
```

Capture 15 independent real-person attempts. Press `SPACE` before every
attempt; invalid sequences are reported and are not saved:

```powershell
python tools\capture_biometric_evaluation_attempt.py `
  --label real --attempts 15 --frames 12 --seconds 4
```

Capture 15 phone-photo attempts after displaying an enrolled photograph
fullscreen on a phone in front of the same camera. Vary distance, angle, and
screen brightness between independent attempts:

```powershell
python tools\capture_biometric_evaluation_attempt.py `
  --label spoof --spoof-type phone_static `
  --attempts 15 --frames 12 --seconds 4
```

Additional attack types can be collected with `--spoof-type printed_photo`,
`tablet_static`, or `replay_video`. The capture utility uses the runtime MTCNN
selection, crop, preprocessing, ONNX model, representative-frame selection,
and median aggregation to reject unusable sequences before writing them. It
stores files only when run explicitly; normal live attendance does not store
frames.

## Optional Passive PAD Evaluation

Evaluate without activating an operating threshold:

```powershell
python tools\evaluate_biometric_security.py `
  --pad-root storage\evaluation\pad_samples `
  --report storage\evaluation\pad-report.json
```

Review the number of attempts, APCER, BPCER, ACER, EER, latency, and attack
coverage. If the dataset is adequate and the tradeoff is accepted, write the
machine-local calibration:

```powershell
python tools\evaluate_biometric_security.py `
  --pad-root storage\evaluation\pad_samples `
  --report storage\evaluation\pad-report.json `
  --write-pad-calibration storage\models\anti_spoof\local-calibration.json `
  --confirm-local-validation
```

Writing a local evaluation calibration requires at least 10 valid real attempts and
10 valid spoof attempts. The selected operating point minimizes ACER, then
uses APCER, BPCER, and the higher threshold as security-oriented tie breakers.
Review all measured metrics and attack coverage rather than accepting a result
only because a file was generated.

Generated calibration remains offline evaluation metadata until a separately
reviewed future PAD integration is implemented. It does not affect the current
live attendance runtime and should never be represented as an active security
control merely because a calibration file exists.

## Readiness Check

Run the read-only preflight before starting the kiosk. It validates required
Python dependencies, the configured MTCNN detector, the FaceNet embedder,
active challenge-response liveness, and a real camera frame. It reports PAD
artifacts as optional information only and does not create or change attendance:

```powershell
.\.venv\Scripts\Activate.ps1
$env:MOBILE_CAMERA_SOURCE="0"
python tools\check_live_attendance_readiness.py
```

Missing or invalid optional PAD calibration does not make readiness fail. A
required active component or the configured camera failing still produces
`LIVE ATTENDANCE READY: NO`.

Set `FACE_SECURITY_DEBUG=true` only for technical diagnosis. The employee kiosk
does not display internal biometric scores or thresholds, and images and
embeddings are not logged.

## Recognition Evaluation

Use independent probe images when possible, including moderate hairstyle,
glasses, lighting, and pose variations:

```powershell
python tools\evaluate_biometric_security.py `
  --recognition-root tests\biometric_samples\recognition `
  --preprocessing legacy `
  --report storage\evaluation\recognition-legacy.json
```

Evaluate alignment separately without changing production embeddings:

```powershell
python tools\evaluate_biometric_security.py `
  --recognition-root tests\biometric_samples\recognition `
  --preprocessing aligned `
  --report storage\evaluation\recognition-aligned.json
```

Do not activate a generated threshold from enrollment images alone. Use a
separate holdout dataset and inspect FAR and FRR before writing a calibration.

## Manual Security Protocol

For each case, record whether active liveness passed, identity matched,
attendance changed, and total latency. PAD may be evaluated separately, but it
is not an enforced runtime result:

1. Real enrolled person, neutral appearance. Expected: pass.
2. Real enrolled person with moderate hairstyle change. Expected: recognize if facial evidence is clear.
3. Real enrolled person with and without normal glasses. Expected: generally recognize after suitable enrollment/evaluation.
4. Wrong real person. Expected: identity rejection.
5. Enrolled photograph displayed on a phone. Record whether active liveness rejects it; rejection is not guaranteed without PAD.
6. Enrolled photograph displayed on a laptop or tablet. Record whether active liveness rejects it; rejection is not guaranteed without PAD.
7. Printed enrolled photograph. Record whether active liveness rejects it; rejection is not guaranteed without PAD.
8. Recorded enrolled-person video. Record whether the randomized challenge rejects it; advanced replay resistance is not guaranteed.
9. Two significant foreground faces. Expected: reject.
10. One primary face with a tiny distant background face. Expected: continue with the primary face.

Before and after each attempt, compare attendance row counts and the target
employee's record. A failed security attempt must not change attendance.

## Known Limitations

- Passive presentation-attack detection is currently not enforced.
- A photograph or replay attack may therefore be more likely to pass than in a fully calibrated PAD deployment.
- The retained RGB PAD module is experimental and is not a certified biometric PAD control.
- Active-liveness and recognition performance is camera, compression, display, lighting, and scene dependent.
- A sophisticated adaptive replay or 3D mask may require depth/IR sensing or a stronger certified model.
- MTCNN supplies five landmarks, which support directional head turns but not reliable eyelid-state measurement. Hardened mode therefore does not offer the old brightness-based blink challenge.
- Any future PAD threshold must be calibrated when the camera, model, crop, or deployment conditions materially change.
