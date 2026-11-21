import 'dart:convert';
import 'dart:io';

import 'api_client.dart';
import 'offline_store.dart';

class SyncResult {
  const SyncResult({required this.synced, required this.pending, this.message});

  final int synced;
  final int pending;
  final String? message;
}

class SyncService {
  SyncService(this.api, this.store);

  final ApiClient api;
  final OfflineStore store;

  Future<SyncResult> synchronize(int ownerId) async {
    var synced = 0;
    String? lastError;
    final pending = await store.pendingRecords(ownerId);
    for (final item in pending) {
      try {
        var evidenceId = item['evidence_id'] as int?;
        if (evidenceId == null) {
          final evidence = await api.uploadEvidence(
            farmId: item['farm_id']! as int,
            unitId: item['unit_id']! as int,
            cycleId: item['cycle_id'] as int?,
            unitTag: item['unit_tag']! as String,
            recordType: item['activity']! as String,
            videoPath: item['video_path']! as String,
            capturedAt: item['captured_at']! as String,
            deviceRecordedAt: item['device_recorded_at']! as String,
            latitude: (item['latitude']! as num).toDouble(),
            longitude: (item['longitude']! as num).toDouble(),
            accuracy: (item['gps_accuracy']! as num).toDouble(),
            challengeId: item['challenge_id'] as int?,
            challengeCode: item['challenge_code'] as String?,
          );
          evidenceId = evidence['id'] as int;
          await store.setEvidenceId(item['id']! as int, evidenceId);
        }

        final body = Map<String, dynamic>.from(
          jsonDecode(item['body_json']! as String) as Map,
        );
        final operation = _operation(item, evidenceId);
        await api.send(
          'POST',
          operation.path,
          body: body,
          query: operation.query,
        );
        await store.removeRecord(item['id']! as int);
        final video = File(item['video_path']! as String);
        if (await video.exists()) await video.delete();
        synced++;
      } on Object catch (error) {
        lastError = error.toString();
        await store.setError(item['id']! as int, lastError);
      }
    }
    return SyncResult(
      synced: synced,
      pending: await store.pendingCount(ownerId),
      message: lastError,
    );
  }

  ({String path, Map<String, String> query}) _operation(
    Map<String, Object?> item,
    int evidenceId,
  ) {
    final farmId = item['farm_id']! as int;
    final unitId = item['unit_id']! as int;
    final cycleId = item['cycle_id'] as int?;
    final root = '/farms/$farmId/units/$unitId';
    switch (item['activity']) {
      case 'stocking':
        return (
          path: '$root/cycles',
          query: {'evidence_id': '$evidenceId'},
        );
      case 'mortality':
        return (
          path: '$root/cycles/$cycleId/mortality',
          query: {'evidence_id': '$evidenceId'},
        );
      case 'growth':
        return (
          path: '$root/cycles/$cycleId/samples',
          query: {'evidence_id': '$evidenceId'},
        );
      case 'water_quality':
        return (
          path: '$root/water-quality',
          query: {'cycle_id': '$cycleId', 'evidence_id': '$evidenceId'},
        );
      case 'feeding':
        return (
          path: '$root/cycles/$cycleId/feeding',
          query: {'evidence_id': '$evidenceId'},
        );
      default:
        throw ApiException('Unsupported offline activity: ${item['activity']}');
    }
  }
}
