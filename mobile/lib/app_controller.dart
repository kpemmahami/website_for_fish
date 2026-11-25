import 'dart:async';
import 'dart:convert';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api_client.dart';
import 'evidence_capture.dart';
import 'offline_store.dart';
import 'sync_service.dart';

class AppController extends ChangeNotifier {
  AppController(this.store);

  static const defaultApiUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://aquafarm-ghana-backend.onrender.com',
  );

  final OfflineStore store;
  late SharedPreferences _preferences;
  late ApiClient api;
  StreamSubscription<List<ConnectivityResult>>? _connectivitySubscription;
  String apiBaseUrl = defaultApiUrl;
  String? token;
  Map<String, dynamic>? user;
  List<Map<String, dynamic>> farms = [];
  List<Map<String, dynamic>> units = [];
  List<Map<String, dynamic>> cycles = [];
  List<Map<String, dynamic>> feeds = [];
  Map<String, dynamic>? dashboard;
  Map<String, dynamic>? analytics;
  int? selectedFarmId;
  int pendingCount = 0;
  String? error;
  String? notice;
  bool loading = false;
  bool syncing = false;
  bool initialized = false;

  Map<String, dynamic>? get selectedFarm {
    for (final farm in farms) {
      if (farm['id'] == selectedFarmId) return farm;
    }
    return null;
  }

  List<Map<String, dynamic>> get activeCycles => cycles
      .where((cycle) => cycle['closed_at'] == null)
      .toList(growable: false);

  Future<void> initialize() async {
    _preferences = await SharedPreferences.getInstance();
    apiBaseUrl = _preferences.getString('api_base_url') ?? defaultApiUrl;
    token = _preferences.getString('access_token');
    api = ApiClient(baseUrl: apiBaseUrl, token: token);
    _connectivitySubscription =
        Connectivity().onConnectivityChanged.listen((results) {
      if (results.any((result) => result != ConnectivityResult.none) &&
          token != null) {
        unawaited(syncPending());
      }
    });
    if (token != null) {
      try {
        user = Map<String, dynamic>.from(await api.get('/auth/me') as Map);
        if (user?['account_type'] != 'pending_farmer') await refresh();
      } on ApiException catch (exception) {
        if (exception.statusCode == 401) {
          await signOut();
        } else {
          error = exception.message;
        }
      } on Object catch (exception) {
        error = exception.toString();
      }
    }
    initialized = true;
    notifyListeners();
  }

  Future<void> configureApiUrl(String value) async {
    final normalized = value.trim().replaceFirst(RegExp(r'/+$'), '');
    final uri = Uri.tryParse(normalized);
    if (uri == null ||
        !const ['https', 'http'].contains(uri.scheme) ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment) {
      throw const ApiException('Enter a valid API address, including http:// or https://.');
    }
    if (normalized == apiBaseUrl) return;
    if (token != null) await signOut();
    apiBaseUrl = normalized;
    await _preferences.setString('api_base_url', apiBaseUrl);
    api.close();
    api = ApiClient(baseUrl: apiBaseUrl, token: token);
    error = null;
    notifyListeners();
  }

  Future<String> requestPasswordRecovery(String email) async {
    final result = await api.send('POST', '/auth/password-recovery/request', body: {
      'portal': 'farmer',
      'email': email.trim(),
    }) as Map;
    return result['message'] as String;
  }

  Future<String?> requestPhoneVerification() async {
    final result = await api.send('POST', '/auth/me/phone-verification/request', body: {}) as Map;
    return result['destination'] as String?;
  }

  Future<void> confirmPhoneVerification(String code) async {
    final result = await api.send('POST', '/auth/me/phone-verification/confirm', body: {'code': code}) as Map;
    final account = user;
    if (account != null) {
      user = {...account, 'phone_verified_at': result['phone_verified_at']};
      notifyListeners();
    }
  }

  Future<List<Map<String, dynamic>>> loadAssignedUnits() async {
    final results = await api.get('/staff/assigned-units') as List;
    return results.map((row) => Map<String, dynamic>.from(row as Map)).toList();
  }

  Future<Map<String, dynamic>> loadStaffFeedingOptions(int farmId, int unitId) async {
    final result = await api.get('/farms/$farmId/units/$unitId/staff-feeding-options') as Map;
    return Map<String, dynamic>.from(result);
  }

  void clearError() {
    error = null;
    notifyListeners();
  }

  void clearMessages() {
    error = null;
    notice = null;
    notifyListeners();
  }

  Future<void> authenticate(String email, String password) async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      final response = Map<String, dynamic>.from(await api.send(
        'POST',
        '/auth/login',
        body: {'email': email.trim(), 'password': password},
      ) as Map);
      token = response['access_token'] as String;
      api.token = token;
      await _preferences.setString('access_token', token!);
      user = Map<String, dynamic>.from(await api.get('/auth/me') as Map);
      if (user?['account_type'] != 'pending_farmer') await refresh();
    } on Object catch (exception) {
      error = exception.toString();
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> registerAndAuthenticate({
    required String fullName,
    required String email,
    required String phoneNumber,
    required String password,
  }) async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      await api.send('POST', '/auth/register', body: {
        'full_name': fullName.trim(),
        'email': email.trim(),
        'phone_number': phoneNumber.trim(),
        'password': password,
      });
      final response = Map<String, dynamic>.from(await api.send(
        'POST',
        '/auth/login',
        body: {'email': email.trim(), 'password': password},
      ) as Map);
      token = response['access_token'] as String;
      api.token = token;
      await _preferences.setString('access_token', token!);
      user = Map<String, dynamic>.from(await api.get('/auth/me') as Map);
      if (user?['account_type'] != 'pending_farmer') await refresh();
    } on Object catch (exception) {
      error = exception.toString();
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> checkApproval() async {
    loading = true;
    error = null;
    notifyListeners();
    try {
      user = Map<String, dynamic>.from(await api.get('/auth/me') as Map);
      if (user?['account_type'] != 'pending_farmer') await refresh();
    } on ApiException catch (exception) {
      if (exception.statusCode == 401) {
        await signOut();
      } else {
        error = exception.message;
      }
    } on Object catch (exception) {
      error = exception.toString();
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> signOut() async {
    token = null;
    user = null;
    farms = [];
    units = [];
    cycles = [];
    feeds = [];
    dashboard = null;
    analytics = null;
    selectedFarmId = null;
    pendingCount = 0;
    await _preferences.remove('access_token');
    api.token = null;
    notifyListeners();
  }

  Future<void> refresh() async {
    if (token == null) return;
    loading = true;
    error = null;
    notifyListeners();
    try {
      final loadedFarms = (await api.get('/farms') as List)
          .map((item) => Map<String, dynamic>.from(item as Map))
          .toList();
      farms = loadedFarms;
      if (loadedFarms.isEmpty) {
        selectedFarmId = null;
        units = [];
        cycles = [];
        dashboard = null;
        analytics = null;
      } else {
        if (!loadedFarms.any((farm) => farm['id'] == selectedFarmId)) {
          selectedFarmId = loadedFarms.first['id'] as int;
        }
        await refreshSelectedFarm();
      }
      await _refreshPendingCount();
    } on Object catch (exception) {
      error = exception.toString();
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> refreshSelectedFarm() async {
    final farmId = selectedFarmId;
    if (farmId == null) return;
    final results = await Future.wait([
      api.get('/farms/$farmId/dashboard/analytics'),
      api.get('/farms/$farmId/units'),
      api.get('/farms/$farmId/feeds'),
    ]);
    dashboard = Map<String, dynamic>.from(results[0] as Map);
    analytics = Map<String, dynamic>.from(results[0] as Map);
    units = (results[1] as List)
        .map((item) => Map<String, dynamic>.from(item as Map))
        .toList();
    feeds = (results[2] as List)
        .map((item) => Map<String, dynamic>.from(item as Map))
        .toList();
    final cycleLists = await Future.wait(units.map((unit) async {
      final unitCycles = await api.get('/farms/$farmId/units/${unit['id']}/cycles');
      return (unitCycles as List).map((item) => {
            ...Map<String, dynamic>.from(item as Map),
            'unit_id': unit['id'],
            'unit_name': unit['name'],
          });
    }));
    cycles = cycleLists.expand((items) => items).toList();
  }

  Future<void> selectFarm(int farmId) async {
    if (farmId == selectedFarmId) return;
    selectedFarmId = farmId;
    loading = true;
    error = null;
    notifyListeners();
    try {
      await refreshSelectedFarm();
    } on Object catch (exception) {
      error = exception.toString();
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<void> createFarm(Map<String, dynamic> body) async {
    final created = await api.send('POST', '/farms', body: body);
    selectedFarmId = created['id'] as int;
    notice = 'Farm registered.';
    await refresh();
  }

  Future<void> createUnit(Map<String, dynamic> body) async {
    final farmId = selectedFarmId;
    if (farmId == null) throw const ApiException('Register a farm first.');
    await api.send('POST', '/farms/$farmId/units', body: body);
    notice = 'Production unit added.';
    await refresh();
  }

  Future<void> queueOperation({
    required String activity,
    required Map<String, dynamic> unit,
    required int? cycleId,
    required Map<String, dynamic> body,
    required EvidenceCapture evidence,
    int? farmId,
  }) async {
    final targetFarmId = farmId ?? selectedFarm?['id'] as int?;
    final currentUser = user;
    if (targetFarmId == null || currentUser == null) {
      throw const ApiException('Select a farm and sign in before recording.');
    }
    await store.queueRecord({
      'owner_id': currentUser['id'] as int,
      'farm_id': targetFarmId,
      'unit_id': unit['id'] as int,
      'cycle_id': cycleId,
      'activity': activity,
      'body_json': jsonEncode(body),
      'video_path': evidence.videoPath,
      'captured_at': evidence.capturedAt,
      'device_recorded_at': evidence.deviceRecordedAt,
      'latitude': evidence.latitude,
      'longitude': evidence.longitude,
      'gps_accuracy': evidence.accuracy,
      'unit_tag': unit['evidence_tag'] as String,
      'challenge_id': evidence.challengeId,
      'challenge_code': evidence.challengeCode,
      'evidence_id': null,
      'last_error': null,
    });
    notice = 'Record saved on this device with its video evidence.';
    await _refreshPendingCount();
    notifyListeners();
    await syncPending();
  }

  Future<void> syncPending() async {
    final currentUser = user;
    if (token == null || currentUser == null || syncing) return;
    syncing = true;
    notifyListeners();
    try {
      final result = await SyncService(api, store)
          .synchronize(currentUser['id'] as int);
      pendingCount = result.pending;
      if (result.synced > 0) {
        notice = 'Synced ${result.synced} offline record${result.synced == 1 ? '' : 's'}.';
        await refreshSelectedFarm();
      }
      if (result.message != null && result.pending > 0) {
        error = 'Some records are still waiting to sync: ${result.message}';
      }
    } on Object catch (exception) {
      error = exception.toString();
      await _refreshPendingCount();
    } finally {
      syncing = false;
      notifyListeners();
    }
  }

  Future<void> prepareOfflineCodes() async {
    final farm = selectedFarm;
    final currentUser = user;
    if (farm == null || currentUser == null) return;
    const activities = ['stocking', 'feeding', 'growth', 'mortality'];
    var prepared = 0;
    final errors = <String>[];
    for (final unit in units) {
      for (final activity in activities) {
        if (await store.hasUsableChallenge(
          ownerId: currentUser['id'] as int,
          unitId: unit['id'] as int,
          activity: activity,
        )) {
          continue;
        }
        try {
          final challenge = Map<String, dynamic>.from(await api.send(
            'POST',
            '/farms/${farm['id']}/evidence-challenges',
            body: {'unit_id': unit['id'], 'activity_type': activity},
          ) as Map);
          await store.cacheChallenge(
            id: challenge['id'] as int,
            ownerId: currentUser['id'] as int,
            unitId: unit['id'] as int,
            activity: activity,
            code: challenge['code'] as String,
            expiresAt: challenge['expires_at'] as String,
          );
          prepared++;
        } on ApiException catch (exception) {
          if (exception.statusCode != 422) errors.add(exception.message);
        }
      }
    }
    if (errors.isNotEmpty) {
      throw ApiException('Could not prepare every offline code: ${errors.first}');
    }
    notice = prepared == 0
        ? 'Valid offline activity codes are already prepared.'
        : 'Prepared $prepared one-time codes for offline activity recording.';
    notifyListeners();
  }

  Future<void> _refreshPendingCount() async {
    final currentUser = user;
    pendingCount = currentUser == null
        ? 0
        : await store.pendingCount(currentUser['id'] as int);
  }

  @override
  void dispose() {
    _connectivitySubscription?.cancel();
    api.close();
    super.dispose();
  }
}
