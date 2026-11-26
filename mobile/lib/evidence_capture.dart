import 'dart:async';
import 'dart:io';

import 'package:camera/camera.dart';
import 'package:material_ui/material_ui.dart';
import 'package:geolocator/geolocator.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';

import 'api_client.dart';
import 'offline_store.dart';

class EvidenceCapture {
  const EvidenceCapture({
    required this.videoPath,
    required this.capturedAt,
    required this.deviceRecordedAt,
    required this.latitude,
    required this.longitude,
    required this.accuracy,
    this.challengeId,
    this.challengeCode,
  });

  final String videoPath;
  final String capturedAt;
  final String deviceRecordedAt;
  final double latitude;
  final double longitude;
  final double accuracy;
  final int? challengeId;
  final String? challengeCode;
}

class EvidenceCapturePage extends StatefulWidget {
  const EvidenceCapturePage({
    required this.api,
    required this.store,
    required this.ownerId,
    required this.farm,
    required this.unit,
    required this.activity,
    this.cycleId,
    this.locationConfigured,
    this.collection = false,
    super.key,
  });

  final ApiClient api;
  final OfflineStore store;
  final int ownerId;
  final Map<String, dynamic> farm;
  final Map<String, dynamic> unit;
  final String activity;
  final int? cycleId;
  final bool? locationConfigured;
  final bool collection;

  @override
  State<EvidenceCapturePage> createState() => _EvidenceCapturePageState();
}

class _EvidenceCapturePageState extends State<EvidenceCapturePage>
    with WidgetsBindingObserver {
  CameraController? _camera;
  List<CameraDescription> _cameras = [];
  CameraDescription? _preferredCamera;
  String? _error;
  String? _controlMessage;
  String? _challengeCode;
  bool _recording = false;
  bool _starting = false;
  bool _opening = false;
  bool _adjusting = false;
  bool _torch = false;
  int _cameraGeneration = 0;
  int _secondsRemaining = 15;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_initializeCamera());
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _camera == null && !_opening) {
      unawaited(_initializeCamera(_preferredCamera));
    } else if (state == AppLifecycleState.paused && _camera != null) {
      _timer?.cancel();
      final previous = _camera!;
      setState(() {
        _cameraGeneration++;
        _camera = null;
        _torch = false;
        if (_recording || _starting) {
          _error = 'Recording interrupted. Please record again.';
        }
        _recording = false;
        _starting = false;
      });
      unawaited(previous.dispose());
    }
  }

  Future<void> _initializeCamera([CameraDescription? requested]) async {
    if (_opening || _recording || _starting || _adjusting) return;
    final generation = ++_cameraGeneration;
    final previous = _camera;
    setState(() {
      _opening = true;
      _camera = null;
      _torch = false;
      _error = null;
      _controlMessage = null;
    });
    try {
      await previous?.dispose();
      final cameras = await availableCameras().timeout(
        const Duration(seconds: 8),
      );
      if (cameras.isEmpty) {
        throw StateError('No camera is available on this device.');
      }
      _cameras = cameras;
      final preferred =
          requested ??
          cameras.firstWhere(
            (camera) => camera.lensDirection == CameraLensDirection.back,
            orElse: () => cameras.first,
          );
      final choices = [
        preferred,
        ...cameras.where((camera) => camera.name != preferred.name),
      ];
      Object? failure;
      for (final camera in choices) {
        if (!mounted || generation != _cameraGeneration) return;
        final controller = CameraController(
          camera,
          ResolutionPreset.medium,
          enableAudio: widget.collection,
        );
        try {
          await controller.initialize().timeout(const Duration(seconds: 8));
        } on Object catch (error) {
          failure = error;
          await controller.dispose();
          continue;
        }
        if (!mounted || generation != _cameraGeneration) {
          await controller.dispose();
          return;
        }
        controller.addListener(() {
          if (mounted &&
              identical(_camera, controller) &&
              controller.value.hasError) {
            final description =
                controller.value.errorDescription ??
                'The camera stopped responding.';
            if (_error != description) setState(() => _error = description);
          }
        });
        setState(() {
          _camera = controller;
          _preferredCamera = camera;
          if (camera.name != preferred.name) {
            _controlMessage = 'Switched to the available camera.';
          }
        });
        return;
      }
      throw failure ?? StateError('Could not open a camera.');
    } on CameraException catch (error) {
      if (mounted && generation == _cameraGeneration) {
        setState(
          () => _error = switch (error.code) {
            'CameraAccessDenied' ||
            'CameraAccessDeniedWithoutPrompt' ||
            'CameraAccessRestricted' =>
              'Allow camera access in Android settings, then tap Retry camera.',
            'AudioAccessDenied' ||
            'AudioAccessDeniedWithoutPrompt' ||
            'AudioAccessRestricted' => 'Allow microphone access in Android settings to record the customer confirmation.',
            _ => error.description ?? 'The camera could not start.',
          },
        );
      }
    } on Object {
      if (mounted && generation == _cameraGeneration) {
        setState(
          () => _error =
              'Camera unavailable. Close any other app using it, then retry.',
        );
      }
    } finally {
      if (mounted && generation == _cameraGeneration) {
        setState(() => _opening = false);
      }
    }
  }

  Future<void> _switchCamera() async {
    final camera = _camera;
    if (camera == null) return;
    final alternatives = _cameras.where(
      (item) =>
          item.name != camera.description.name &&
          item.lensDirection != camera.description.lensDirection,
    );
    if (alternatives.isNotEmpty) await _initializeCamera(alternatives.first);
  }

  Future<void> _toggleTorch() async {
    final camera = _camera;
    if (camera == null || _adjusting) return;
    final next = !_torch;
    setState(() {
      _adjusting = true;
      _controlMessage = null;
    });
    try {
      await camera.setFlashMode(next ? FlashMode.torch : FlashMode.off);
      if (mounted && identical(_camera, camera)) setState(() => _torch = next);
    } on CameraException {
      if (mounted) {
        setState(
          () => _controlMessage = 'This camera does not provide a video light.',
        );
      }
    } finally {
      if (mounted) setState(() => _adjusting = false);
    }
  }

  Future<Map<String, Object?>?> _prepareChallenge() async {
    const challengeActivities = {'stocking', 'feeding', 'growth', 'mortality'};
    if (!challengeActivities.contains(widget.activity)) return null;
    try {
      final response = await widget.api.send(
        'POST',
        '/farms/${widget.farm['id']}/evidence-challenges',
        body: {'unit_id': widget.unit['id'], 'activity_type': widget.activity},
      );
      return {'id': response['id'], 'code': response['code']};
    } on ApiException catch (error) {
      if (error.statusCode == 422) return null;
      final cached = await widget.store.takeChallenge(
        ownerId: widget.ownerId,
        unitId: widget.unit['id'] as int,
        activity: widget.activity,
      );
      if (cached != null) return cached;
      rethrow;
    } on Object {
      final cached = await widget.store.takeChallenge(
        ownerId: widget.ownerId,
        unitId: widget.unit['id'] as int,
        activity: widget.activity,
      );
      if (cached != null) return cached;
      rethrow;
    }
  }

  Future<Position> _getPosition() async {
    final unitHasLocation =
        widget.unit['latitude'] != null && widget.unit['longitude'] != null;
    final farmHasLocation =
        widget.farm['latitude'] != null && widget.farm['longitude'] != null;
    if (!(widget.locationConfigured ?? (unitHasLocation || farmHasLocation))) {
      throw Exception(
        'Add GPS coordinates to the farm or unit before recording evidence.',
      );
    }
    if (!await Geolocator.isLocationServiceEnabled()) {
      throw Exception('Turn on device location services and try again.');
    }
    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.denied ||
        permission == LocationPermission.deniedForever) {
      throw Exception('Location permission is required for farm evidence.');
    }
    final position = await Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.high,
        timeLimit: Duration(seconds: 25),
      ),
    );
    if (position.accuracy > 1000) {
      throw Exception(
        'GPS accuracy is too low. Move to a clearer location and try again.',
      );
    }
    return position;
  }

  Future<void> _record() async {
    final camera = _camera;
    if (camera == null ||
        !camera.value.isInitialized ||
        _recording ||
        _starting ||
        _adjusting) {
      return;
    }
    setState(() {
      _starting = true;
      _error = null;
      _secondsRemaining = 15;
    });
    try {
      final challenge = widget.collection ? null : await _prepareChallenge();
      final position = widget.collection ? null : await _getPosition();
      if (!mounted || !identical(_camera, camera)) return;
      final capturedAt = DateTime.now().toUtc().toIso8601String();
      setState(() {
        _challengeCode = challenge?['code'] as String?;
      });
      await camera.startVideoRecording();
      if (!mounted || !identical(_camera, camera)) return;
      setState(() => _recording = true);
      var elapsed = 0;
      _timer?.cancel();
      _timer = Timer.periodic(const Duration(seconds: 1), (timer) {
        elapsed++;
        if (mounted) {
          setState(() => _secondsRemaining = 15 - elapsed);
        }
        if (elapsed >= 15) {
          timer.cancel();
          unawaited(
            _finishRecording(
              camera: camera,
              position: position,
              capturedAt: capturedAt,
              challenge: challenge,
            ),
          );
        }
      });
    } on Object catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _starting = false);
    }
  }

  Future<void> _finishRecording({
    required CameraController camera,
    required Position? position,
    required String capturedAt,
    required Map<String, Object?>? challenge,
  }) async {
    try {
      final clip = await camera.stopVideoRecording();
      final source = File(clip.path);
      final size = await source.length();
      if (size == 0) {
        throw Exception('The recording is empty. Please try again.');
      }
      if (size > 30 * 1024 * 1024) {
        throw Exception(
          'Video exceeds the 30 MB upload limit. Record again closer to the activity.',
        );
      }
      final directory = await getApplicationDocumentsDirectory();
      final destination = path.join(
        directory.path,
        'evidence_${DateTime.now().toUtc().microsecondsSinceEpoch}.mp4',
      );
      await source.copy(destination);
      await source.delete();
      if (!mounted) return;
      setState(() => _recording = false);
      Navigator.of(context).pop(
        EvidenceCapture(
          videoPath: destination,
          capturedAt: capturedAt,
          deviceRecordedAt: DateTime.now().toUtc().toIso8601String(),
          latitude: position?.latitude ?? 0,
          longitude: position?.longitude ?? 0,
          accuracy: position == null || position.accuracy < 1
              ? 1
              : position.accuracy,
          challengeId: challenge?['id'] as int?,
          challengeCode: challenge?['code'] as String?,
        ),
      );
    } on Object catch (error) {
      if (mounted) {
        setState(() {
          _recording = false;
          _error = error.toString();
        });
      }
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _cameraGeneration++;
    _timer?.cancel();
    _camera?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final camera = _camera;
    final ready = camera?.value.isInitialized == true && !camera!.value.hasError;
    final canSwitch =
        camera != null &&
        _cameras.any(
          (item) => item.lensDirection != camera.description.lensDirection,
        );
    const navy = Color(0xff113042);
    const teal = Color(0xff007d74);
    return PopScope(
      canPop: !_starting && !_recording,
      child: Scaffold(
        backgroundColor: const Color(0xffedf6f4),
        appBar: AppBar(
          backgroundColor: navy,
          foregroundColor: Colors.white,
          title: Text(
            widget.collection ? 'Collection video' : 'Record activity evidence',
          ),
        ),
        body: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Text(
              'Record a new 15-second video for ${widget.activity.replaceAll('_', ' ')}.',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            Text(
              widget.collection
                  ? 'State the amount received and ask the customer to confirm it on camera.'
                  : 'Gallery uploads are not accepted. Keep the farm activity and pond/unit in view.',
            ),
            const SizedBox(height: 16),
            ClipRRect(
              borderRadius: BorderRadius.circular(18),
              child: ColoredBox(
                color: navy,
                child: AspectRatio(
                  aspectRatio: ready
                      ? (MediaQuery.orientationOf(context) ==
                                Orientation.portrait
                            ? 1 / camera.value.aspectRatio
                            : camera.value.aspectRatio)
                      : 4 / 3,
                  child: ready
                      ? CameraPreview(camera)
                      : Center(
                          child: _opening
                              ? const CircularProgressIndicator(
                                  color: Colors.white,
                                )
                              : const Icon(
                                  Icons.videocam_off_outlined,
                                  color: Colors.white,
                                  size: 42,
                                ),
                        ),
                ),
              ),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                OutlinedButton.icon(
                  onPressed:
                      ready &&
                          canSwitch &&
                          !_recording &&
                          !_starting &&
                          !_adjusting
                      ? _switchCamera
                      : null,
                  icon: const Icon(Icons.cameraswitch_outlined),
                  label: Text(
                    camera?.description.lensDirection ==
                            CameraLensDirection.front
                        ? 'Rear camera'
                        : 'Front camera',
                  ),
                ),
                OutlinedButton.icon(
                  onPressed:
                      ready &&
                          !_adjusting &&
                          camera.description.lensDirection ==
                              CameraLensDirection.back
                      ? _toggleTorch
                      : null,
                  icon: Icon(
                    _torch ? Icons.flashlight_off : Icons.flashlight_on,
                  ),
                  label: Text(_torch ? 'Light off' : 'Light on'),
                ),
                if (!ready && !_opening && !_recording && !_starting)
                  OutlinedButton.icon(
                    onPressed: () => _initializeCamera(_preferredCamera),
                    icon: const Icon(Icons.refresh),
                    label: const Text('Retry camera'),
                  ),
              ],
            ),
            if (_controlMessage != null) Text(_controlMessage!),
            if (_challengeCode != null) ...[
              const SizedBox(height: 12),
              Card(
                color: Theme.of(context).colorScheme.secondaryContainer,
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Text(
                    'One-time activity code: $_challengeCode. Show or say it in the video.',
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                ),
              ),
            ],
            if (_recording) ...[
              const SizedBox(height: 16),
              LinearProgressIndicator(value: (15 - _secondsRemaining) / 15),
              const SizedBox(height: 8),
              Center(
                child: Text(
                  'Recording… $_secondsRemaining seconds remaining',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
            ],
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ],
            const SizedBox(height: 20),
            FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: teal,
                foregroundColor: Colors.white,
              ),
              onPressed: ready && !_recording && !_starting && !_adjusting
                  ? _record
                  : null,
              icon: const Icon(Icons.fiber_manual_record),
              label: const Text('Capture required video'),
            ),
            if (!_recording && !_starting)
              TextButton(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('Cancel'),
              ),
          ],
        ),
      ),
    );
  }
}
