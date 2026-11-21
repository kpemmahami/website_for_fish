import 'dart:convert';

import 'package:path/path.dart' as path;
import 'package:sqflite/sqflite.dart';

class OfflineStore {
  Database? _database;

  Future<Database> get database async {
    if (_database != null) return _database!;
    final location = path.join(await getDatabasesPath(), 'aquafarm_mobile.db');
    _database = await openDatabase(
      location,
      version: 1,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE pending_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            farm_id INTEGER NOT NULL,
            unit_id INTEGER NOT NULL,
            cycle_id INTEGER,
            activity TEXT NOT NULL,
            body_json TEXT NOT NULL,
            video_path TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            device_recorded_at TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            gps_accuracy REAL NOT NULL,
            unit_tag TEXT NOT NULL,
            challenge_id INTEGER,
            challenge_code TEXT,
            evidence_id INTEGER,
            last_error TEXT,
            created_at TEXT NOT NULL
          )
        ''');
        await db.execute('''
          CREATE TABLE cached_challenges (
            id INTEGER PRIMARY KEY,
            owner_id INTEGER NOT NULL,
            unit_id INTEGER NOT NULL,
            activity TEXT NOT NULL,
            code TEXT NOT NULL,
            expires_at TEXT NOT NULL
          )
        ''');
      },
    );
    return _database!;
  }

  Future<int> queueRecord(Map<String, Object?> record) async {
    final db = await database;
    return db.insert('pending_records', {
      ...record,
      'created_at': DateTime.now().toUtc().toIso8601String(),
    });
  }

  Future<List<Map<String, Object?>>> pendingRecords(int ownerId) async {
    final db = await database;
    return db.query(
      'pending_records',
      where: 'owner_id = ?',
      whereArgs: [ownerId],
      orderBy: 'created_at ASC, id ASC',
    );
  }

  Future<int> pendingCount(int ownerId) async =>
      (await pendingRecords(ownerId)).length;

  Future<void> setEvidenceId(int id, int evidenceId) async {
    final db = await database;
    await db.update(
      'pending_records',
      {'evidence_id': evidenceId, 'last_error': null},
      where: 'id = ?',
      whereArgs: [id],
    );
  }

  Future<void> setError(int id, String message) async {
    final db = await database;
    await db.update(
      'pending_records',
      {'last_error': message},
      where: 'id = ?',
      whereArgs: [id],
    );
  }

  Future<void> removeRecord(int id) async {
    final db = await database;
    await db.delete('pending_records', where: 'id = ?', whereArgs: [id]);
  }

  Future<void> cacheChallenge({
    required int id,
    required int ownerId,
    required int unitId,
    required String activity,
    required String code,
    required String expiresAt,
  }) async {
    final db = await database;
    await db.insert(
      'cached_challenges',
      {
        'id': id,
        'owner_id': ownerId,
        'unit_id': unitId,
        'activity': activity,
        'code': code,
        'expires_at': expiresAt,
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<bool> hasUsableChallenge({
    required int ownerId,
    required int unitId,
    required String activity,
  }) async {
    final db = await database;
    final rows = await db.query(
      'cached_challenges',
      where: 'owner_id = ? AND unit_id = ? AND activity = ? AND expires_at > ?',
      whereArgs: [
        ownerId,
        unitId,
        activity,
        DateTime.now().toUtc().toIso8601String(),
      ],
      limit: 1,
    );
    return rows.isNotEmpty;
  }

  Future<Map<String, Object?>?> takeChallenge({
    required int ownerId,
    required int unitId,
    required String activity,
  }) async {
    final db = await database;
    return db.transaction((transaction) async {
      final rows = await transaction.query(
        'cached_challenges',
        where: 'owner_id = ? AND unit_id = ? AND activity = ? AND expires_at > ?',
        whereArgs: [
          ownerId,
          unitId,
          activity,
          DateTime.now().toUtc().toIso8601String(),
        ],
        orderBy: 'expires_at ASC',
        limit: 1,
      );
      if (rows.isEmpty) return null;
      final challenge = rows.first;
      await transaction.delete(
        'cached_challenges',
        where: 'id = ?',
        whereArgs: [challenge['id']],
      );
      return challenge;
    });
  }

  Map<String, Object?> decodeRecord(Map<String, Object?> row) => {
        ...row,
        'body': jsonDecode(row['body_json']! as String),
      };
}
