import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({required this.baseUrl, this.token, http.Client? client})
    : _client = client ?? http.Client();

  String baseUrl;
  String? token;
  final http.Client _client;

  Uri _uri(String path, [Map<String, String>? query]) {
    final normalizedBase = baseUrl.trim().replaceFirst(RegExp(r'/+$'), '');
    final normalizedPath = path.replaceFirst(RegExp(r'^/+'), '');
    return Uri.parse('$normalizedBase/$normalizedPath')
        .replace(queryParameters: query);
  }

  Future<dynamic> get(String path) => request('GET', path);

  Future<dynamic> send(
    String method,
    String path, {
    Map<String, dynamic>? body,
    Map<String, String>? query,
  }) => request(method, path, body: body, query: query);

  Future<dynamic> request(
    String method,
    String path, {
    Map<String, dynamic>? body,
    Map<String, String>? query,
  }) async {
    final request = http.Request(method, _uri(path, query));
    _addHeaders(request.headers, 'application/json');
    if (body != null) request.body = jsonEncode(body);
    return _send(request);
  }

  Future<dynamic> uploadEvidence({
    required int farmId,
    required int unitId,
    required int? cycleId,
    required String unitTag,
    required String recordType,
    required String videoPath,
    required String capturedAt,
    required String deviceRecordedAt,
    required double latitude,
    required double longitude,
    required double accuracy,
    int? challengeId,
    String? challengeCode,
  }) async {
    final query = <String, String>{
      'unit_id': '$unitId',
      'unit_tag': unitTag,
      'record_type': recordType,
      'captured_at': capturedAt,
      'device_recorded_at': deviceRecordedAt,
      'latitude': '$latitude',
      'longitude': '$longitude',
      'gps_accuracy_m': '$accuracy',
      'duration_seconds': '15',
    };
    if (cycleId != null) query['cycle_id'] = '$cycleId';
    if (challengeId != null) query['challenge_id'] = '$challengeId';
    if (challengeCode != null) query['challenge_code'] = challengeCode;

    final request = http.Request(
      'POST',
      _uri('/farms/$farmId/evidence', query),
    );
    final extension = videoPath.toLowerCase().endsWith('.mp4') ? 'mp4' : 'webm';
    request.headers['Content-Type'] = extension == 'mp4'
        ? 'video/mp4'
        : 'video/webm';
    if (token != null) request.headers['Authorization'] = 'Bearer $token';
    request.bodyBytes = await File(videoPath).readAsBytes();
    return _send(request, timeout: const Duration(minutes: 2));
  }

  Future<int> uploadCollectionVideo(
    int loanId,
    String path,
    String capturedAt,
    String deviceRecordedAt, {
    String kind = 'repayment',
  }) async {
    final request = http.Request(
      'POST',
      _uri('/finance/loans/$loanId/evidence', {
        'record_type': kind,
        'captured_at': capturedAt,
        'device_recorded_at': deviceRecordedAt,
        'duration_seconds': '15',
        'retry_upload': 'true',
      }),
    );
    _addHeaders(request.headers, 'video/mp4');
    request.bodyBytes = await File(path).readAsBytes();
    final result =
        await _send(request, timeout: const Duration(minutes: 2)) as Map;
    return result['id'] as int;
  }

  void _addHeaders(Map<String, String> headers, String contentType) {
    headers['Content-Type'] = contentType;
    if (token != null) headers['Authorization'] = 'Bearer $token';
  }

  Future<dynamic> _send(
    http.BaseRequest request, {
    Duration timeout = const Duration(seconds: 35),
  }) async {
    try {
      final streamed = await _client.send(request).timeout(timeout);
      final response = await http.Response.fromStream(streamed);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        var message = 'Request failed (${response.statusCode})';
        try {
          final decoded = jsonDecode(response.body);
          final detail = decoded is Map ? decoded['detail'] : null;
          if (detail is String && detail.isNotEmpty) {
            message = detail;
          } else if (detail != null) {
            message = jsonEncode(detail);
          }
        } on FormatException {
          if (response.body.isNotEmpty) message = response.body;
        }
        throw ApiException(message, statusCode: response.statusCode);
      }
      if (response.statusCode == 204 || response.body.isEmpty) return null;
      return jsonDecode(response.body);
    } on ApiException {
      rethrow;
    } on TimeoutException {
      throw const ApiException('The API request timed out. It can be retried.');
    } on http.ClientException catch (error) {
      throw ApiException('Cannot reach the API: ${error.message}');
    } on FormatException {
      throw const ApiException('The API returned an invalid response.');
    }
  }

  void close() => _client.close();
}
