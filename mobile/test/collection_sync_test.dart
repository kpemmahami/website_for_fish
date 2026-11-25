import 'dart:convert';

import 'package:aquafarm_mobile/api_client.dart';
import 'package:aquafarm_mobile/app_controller.dart';
import 'package:aquafarm_mobile/collection_entry.dart';
import 'package:aquafarm_mobile/offline_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class MemoryCollections extends OfflineStore {
  final row = <String, Object?>{
    'collection_id': '9e97bd6f-86d1-4a35-90cb-e47f96ac5243',
    'loan_id': 4,
    'amount': '25.00',
    'video_path': 'test-collection-video.mp4',
    'captured_at': '2026-11-25T12:00:00Z',
    'device_recorded_at': '2026-11-25T12:00:15Z',
    'evidence_id': 30,
  };
  bool removed = false;

  @override
  Future<List<Map<String, Object?>>> pendingCollections(String scope) async =>
      !removed && scope == 'test-scope' ? [Map.of(row)] : [];

  @override
  Future<void> updateCollection(
    String scope,
    String id,
    Map<String, Object?> values,
  ) async {
    row.addAll(values);
  }

  @override
  Future<void> removeCollection(String scope, String id) async {
    removed = true;
  }
}

void main() {
  test('manual sync retains a failed collection and retries with the same reference', () async {
    final store = MemoryCollections();
    final controller = AppController(store)..token = 'test-token';
    var requests = 0;
    controller.api = ApiClient(
      baseUrl: 'https://example.com',
      token: controller.token,
      client: MockClient((request) async {
        expect(request.url.path, '/finance/loans/4/field-repayments');
        expect(jsonDecode(request.body), {
          'collection_id': store.row['collection_id'],
          'amount_ghs': '25.00',
          'transaction_date': '2026-11-25',
          'customer_consented': true,
          'evidence_id': 30,
        });
        requests++;
        return requests == 1
            ? http.Response('{"detail":"Try again"}', 503)
            : http.Response('{"id":8}', 200);
      }),
    );
    expect(await syncCollections(controller, 'other-scope'), 0);
    expect(await syncCollections(controller, 'test-scope'), 0);
    expect(store.removed, isFalse);
    expect(store.row['last_error'], 'Try again');
    expect(await syncCollections(controller, 'test-scope'), 1);
    expect(store.removed, isTrue);
    expect(requests, 2);
    controller.dispose();
  });
}
