import 'package:material_ui/material_ui.dart';

import 'app_controller.dart';
import 'evidence_capture.dart';

class StaffFeedingPage extends StatefulWidget {
  const StaffFeedingPage({
    required this.controller,
    required this.assignment,
    super.key,
  });

  final AppController controller;
  final Map<String, dynamic> assignment;

  @override
  State<StaffFeedingPage> createState() => _StaffFeedingPageState();
}

class _StaffFeedingPageState extends State<StaffFeedingPage> {
  final _form = GlobalKey<FormState>();
  final _quantity = TextEditingController();
  final _tag = TextEditingController();
  final _notes = TextEditingController();
  late final _options = widget.controller.loadStaffFeedingOptions(
    _farmId,
    _unitId,
  );
  int? _cycleId;
  int? _feedId;
  bool _busy = false;
  String? _error;

  int get _farmId => widget.assignment['farm_id'] as int;
  int get _unitId => widget.assignment['unit_id'] as int;

  @override
  void dispose() {
    _quantity.dispose();
    _tag.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _capture() async {
    if (!_form.currentState!.validate() ||
        _cycleId == null ||
        _feedId == null) {
      return;
    }
    final user = widget.controller.user;
    if (user == null) return;
    final farm = {'id': _farmId, 'name': widget.assignment['farm_name']};
    final unit = {
      'id': _unitId,
      'name': widget.assignment['unit_name'],
      'evidence_tag': _tag.text.trim(),
    };
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final options = await _options;
      if (!mounted) return;
      final evidence = await Navigator.of(context).push<EvidenceCapture>(
        MaterialPageRoute(
          builder: (_) => EvidenceCapturePage(
            api: widget.controller.api,
            store: widget.controller.store,
            ownerId: user['id'] as int,
            farm: farm,
            unit: unit,
            activity: 'feeding',
            cycleId: _cycleId,
            locationConfigured: options['location_configured'] == true,
          ),
        ),
      );
      if (!mounted || evidence == null) return;
      final capturedDate = DateTime.parse(evidence.capturedAt)
          .toUtc()
          .toIso8601String()
          .substring(0, 10);
      await widget.controller.queueOperation(
        farmId: _farmId,
        unit: unit,
        cycleId: _cycleId,
        activity: 'feeding',
        evidence: evidence,
        body: {
          'feed_id': _feedId,
          'quantity_kg': double.parse(_quantity.text.trim()),
          'fed_on': capturedDate,
          'actual_fed_at': evidence.capturedAt,
          'notes': _notes.text.trim(),
        },
      );
      if (!mounted) return;
      final message =
          widget.controller.error ??
          widget.controller.notice ??
          'Feeding record saved.';
      Navigator.pop(context, message);
    } on Object catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Record assigned feeding')),
    body: FutureBuilder(
      future: _options,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return Center(child: Text(snapshot.error.toString()));
        }
        final options = snapshot.requireData;
        final cycles = options['cycles'] as List;
        final feeds = options['feeds'] as List;
        if (options['location_configured'] != true ||
            cycles.isEmpty ||
            feeds.isEmpty) {
          return const Center(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: Text(
                'Ask the farm owner to check the unit’s GPS location, active cycle, and feed products.',
              ),
            ),
          );
        }
        return Form(
          key: _form,
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              Text(
                widget.assignment['unit_name'] as String,
                style: Theme.of(context).textTheme.titleLarge,
              ),
              DropdownButtonFormField<int>(
                decoration: const InputDecoration(
                  labelText: 'Active stocking cycle',
                ),
                items: [
                  for (final cycle in cycles)
                    DropdownMenuItem(
                      value: cycle['id'] as int,
                      child: Text(
                        "${cycle['species']} · ${cycle['stocked_on']}",
                      ),
                    ),
                ],
                onChanged: _busy ? null : (value) => _cycleId = value,
                validator: (value) =>
                    value == null ? 'Select an active stocking cycle' : null,
              ),
              DropdownButtonFormField<int>(
                decoration: const InputDecoration(labelText: 'Feed product'),
                items: [
                  for (final feed in feeds)
                    DropdownMenuItem(
                      value: feed['id'] as int,
                      child: Text(feed['name'] as String),
                    ),
                ],
                onChanged: _busy ? null : (value) => _feedId = value,
                validator: (value) =>
                    value == null ? 'Select a feed product' : null,
              ),
              TextFormField(
                controller: _quantity,
                enabled: !_busy,
                decoration: const InputDecoration(
                  labelText: 'Feed quantity (kg)',
                ),
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                validator: (value) {
                  final quantity = double.tryParse(value?.trim() ?? '');
                  return quantity == null || !quantity.isFinite || quantity <= 0
                      ? 'Enter a positive quantity'
                      : null;
                },
              ),
              TextFormField(
                controller: _tag,
                enabled: !_busy,
                maxLength: 32,
                decoration: const InputDecoration(
                  labelText: 'Physical unit tag',
                ),
                validator: (value) => value?.trim().isNotEmpty == true
                    ? null
                    : 'Enter the tag shown on this unit',
              ),
              TextFormField(
                controller: _notes,
                enabled: !_busy,
                maxLength: 1000,
                decoration: const InputDecoration(
                  labelText: 'Feeding notes',
                  helperText: 'If the unit has a schedule, explain why this feeding was unscheduled.',
                ),
              ),
              if (_error != null)
                Semantics(liveRegion: true, child: Text(_error!)),
              FilledButton(
                onPressed: _busy ? null : _capture,
                child: const Text('Record evidence video'),
              ),
            ],
          ),
        );
      },
    ),
  );
}
