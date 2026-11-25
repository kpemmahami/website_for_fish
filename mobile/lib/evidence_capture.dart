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

class _EvidenceCapturePageState extends State<EvidenceCapturePage> {
  CameraController? _camera;
  String? _error;
  String? _challengeCode;
  bool _recording = false;
  int _secondsRemaining = 15;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _initializeCamera();
  }

  Future<void> _initializeCamera() async {
    try {
      final cameras = await availableCameras();
      if (cameras.isEmpty) throw Exception('No camera is available.');
      final selected = cameras.firstWhere(
        (camera) => camera.lensDirection == CameraLensDirection.back,
        orElse: () => cameras.first,
      );
      final controller = CameraController(
        selected,
        ResolutionPreset.medium,
        enableAudio: widget.collection,
      );
      await controller.initialize();
      if (!mounted) {
        await controller.dispose();
        return;
      }
      setState(() => _camera = controller);
    } on Object catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  Future<Map<String, Object?>?> _prepareChallenge() async {
    const challengeActivities = {'stocking', 'feeding', 'growth', 'mortality'};
    if (!challengeActivities.contains(widget.activity)) return null;
    try {
      final response = await widget.api.send(
        'POST',
        '/farms/${widget.farm['id']}/evidence-challenges',
        body: {
          'unit_id': widget.unit['id'],
          'activity_type': widget.activity,
        },
      );
      return {
        'id': response['id'],
        'code': response['code'],
      };
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
      throw Exception('Add GPS coordinates to the farm or unit before recording evidence.');
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
      throw Exception('GPS accuracy is too low. Move to a clearer location and try again.');
    }
    return position;
  }

  Future<void> _record() async {
    final camera = _camera;
    if (camera == null || !camera.value.isInitialized || _recording) return;
    setState(() {
      _error = null;
      _secondsRemaining = 15;
    });
    try {
      final challenge = widget.collection ? null : await _prepareChallenge();
      final position = widget.collection ? null : await _getPosition();
      if (!mounted) return;
      final capturedAt = DateTime.now().toUtc().toIso8601String();
      setState(() {
        _challengeCode = challenge?['code'] as String?;
      });
      await camera.startVideoRecording();
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
          unawaited(_finishRecording(
            camera: camera,
            position: position,
            capturedAt: capturedAt,
            challenge: challenge,
          ));
        }
      });
    } on Object catch (error) {
      if (mounted) setState(() => _error = error.toString());
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
      if (size == 0) throw Exception('The recording is empty. Please try again.');
      if (size > 30 * 1024 * 1024) {
        throw Exception('Video exceeds the 30 MB upload limit. Record again closer to the activity.');
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
      Navigator.of(context).pop(EvidenceCapture(
        videoPath: destination,
        capturedAt: capturedAt,
        deviceRecordedAt: DateTime.now().toUtc().toIso8601String(),
        latitude: position?.latitude ?? 0,
        longitude: position?.longitude ?? 0,
        accuracy: position == null || position.accuracy < 1 ? 1 : position.accuracy,
        challengeId: challenge?['id'] as int?,
        challengeCode: challenge?['code'] as String?,
      ));
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
    _timer?.cancel();
    _camera?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final camera = _camera;
    return Scaffold(
      appBar: AppBar(title: const Text('Record activity evidence')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text(
            'Record a new 15-second video for ${widget.activity.replaceAll('_', ' ')}.',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          Text(widget.collection
            ? 'State the amount received and ask the customer to confirm it on camera.'
            : 'Gallery uploads are not accepted. Keep the farm activity and pond/unit in view.'),
          const SizedBox(height: 16),
          AspectRatio(
            aspectRatio: camera?.value.isInitialized == true
                ? camera!.value.aspectRatio
                : 4 / 3,
            child: camera?.value.isInitialized == true
                ? ClipRRect(
                    borderRadius: BorderRadius.circular(16),
                    child: CameraPreview(camera!),
                  )
                : const Center(child: CircularProgressIndicator()),
          ),
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
            Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ],
          const SizedBox(height: 20),
          FilledButton.icon(
            onPressed: camera?.value.isInitialized == true && !_recording
                ? _record
                : null,
            icon: const Icon(Icons.fiber_manual_record),
            label: const Text('Capture required video'),
          ),
          if (!_recording)
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Cancel'),
            ),
        ],
      ),
    );
  }
}
