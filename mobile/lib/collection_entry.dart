import 'dart:io';
import 'dart:math';

import 'package:material_ui/material_ui.dart';

import 'app_controller.dart';
import 'evidence_capture.dart';

String newCollectionId() {
  final random = Random.secure();
  final bytes = List.generate(16, (_) => random.nextInt(256));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  final hex = bytes
      .map((byte) => byte.toRadixString(16).padLeft(2, '0'))
      .join();
  return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
}

class CollectionEntry extends StatefulWidget {
  const CollectionEntry({
    required this.controller,
    required this.scope,
    required this.loan,
    super.key,
  });

  final AppController controller;
  final String scope;
  final Map loan;

  @override
  State<CollectionEntry> createState() => _CollectionEntryState();
}

class _CollectionEntryState extends State<CollectionEntry> {
  final _amount = TextEditingController();
  bool _consent = false;
  bool _busy = false;
  String? _error;
  EvidenceCapture? _clip;

  @override
  void dispose() {
    _amount.dispose();
    final clip = _clip;
    if (clip != null) File(clip.videoPath).delete().ignore();
    super.dispose();
  }

  bool get _validAmount {
    final amount = _amount.text.trim();
    return RegExp(r'^\d{1,12}(\.\d{1,2})?$').hasMatch(amount) &&
        double.parse(amount) > 0;
  }

  Future<void> _capture() async {
    if (!_consent || !_validAmount || _busy) return;
    final clip = await Navigator.of(context).push<EvidenceCapture>(
      MaterialPageRoute(
        builder: (_) => EvidenceCapturePage(
          api: widget.controller.api,
          store: widget.controller.store,
          ownerId: widget.controller.user!['id'] as int,
          farm: const {},
          unit: const {},
          activity: 'loan repayment',
          collection: true,
        ),
      ),
    );
    if (clip == null) return;
    if (!mounted) {
      await File(clip.videoPath).delete();
      return;
    }
    setState(() => _clip = clip);
  }

  Future<void> _save() async {
    final clip = _clip;
    if (clip == null || !_consent || !_validAmount || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.controller.store.queueCollection({
        'collection_id': newCollectionId(),
        'scope': widget.scope,
        'loan_id': widget.loan['loan_id'],
        'amount': _amount.text.trim(),
        'video_path': clip.videoPath,
        'captured_at': clip.capturedAt,
        'device_recorded_at': clip.deviceRecordedAt,
      });
      _clip = null;
      if (mounted) Navigator.of(context).pop(true);
    } on Object catch (error) {
      if (mounted) {
        setState(() {
          _busy = false;
          _error = error.toString();
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: !_busy || _clip == null,
    child: Scaffold(
      appBar: AppBar(title: const Text('Collect loan repayment')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text(
            '${widget.loan['customer_name']} · ${widget.loan['account_number']}',
          ),
          TextField(
            controller: _amount,
            enabled: _clip == null && !_busy,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(
              labelText: 'Amount received (GHS)',
            ),
            onChanged: (_) => setState(() {}),
          ),
          CheckboxListTile(
            value: _consent,
            onChanged: _clip != null || _busy
                ? null
                : (value) => setState(() => _consent = value == true),
            title: const Text(
              'The customer consents to video confirmation of the amount received.',
            ),
          ),
          if (_clip == null)
            OutlinedButton(
              onPressed: _consent && _validAmount && !_busy ? _capture : null,
              child: const Text('Record confirmation video'),
            )
          else
            const Text('Confirmation video captured'),
          if (_error != null) Text(_error!),
          FilledButton(
            onPressed: _clip == null || _busy ? null : _save,
            child: const Text('Save to sync queue'),
          ),
        ],
      ),
    ),
  );
}

Future<int> syncCollections(AppController controller, String scope) async {
  final api = controller.api;
  final token = controller.token;
  var synced = 0;
  for (final row in await controller.store.pendingCollections(scope)) {
    if (token == null || controller.token != token || controller.api != api) {
      break;
    }
    final id = row['collection_id'] as String;
    final loanId = row['loan_id'] as int;
    final path = row['video_path'] as String;
    final capturedAt = row['captured_at'] as String;
    try {
      final evidence =
          (row['evidence_id'] as int?) ??
          await api.uploadCollectionVideo(
            loanId,
            path,
            capturedAt,
            row['device_recorded_at'] as String,
          );
      await controller.store.updateCollection(scope, id, {
        'evidence_id': evidence,
      });
      if (controller.token != token || controller.api != api) break;
      await api.send(
        'POST',
        '/finance/loans/$loanId/field-repayments',
        body: {
          'collection_id': id,
          'amount_ghs': row['amount'],
          'transaction_date': capturedAt.substring(0, 10),
          'customer_consented': true,
          'evidence_id': evidence,
        },
      );
      await controller.store.removeCollection(scope, id);
      await File(path).delete().catchError((Object _) => File(path));
      synced++;
    } on Object catch (error) {
      await controller.store.updateCollection(scope, id, {
        'last_error': error.toString(),
      });
    }
  }
  return synced;
}
