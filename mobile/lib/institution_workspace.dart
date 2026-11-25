import 'package:material_ui/material_ui.dart';
import 'package:flutter/services.dart';

import 'app_controller.dart';
import 'collection_entry.dart';
import 'api_client.dart';

class InstitutionSignIn extends StatefulWidget {
  const InstitutionSignIn({required this.controller, super.key});

  final AppController controller;

  @override
  State<InstitutionSignIn> createState() => _InstitutionSignInState();
}

class _InstitutionSignInState extends State<InstitutionSignIn> {
  final _form = GlobalKey<FormState>();
  final _identifier = TextEditingController();
  final _password = TextEditingController();
  final _code = TextEditingController();
  String? _challenge;
  bool _initialPassword = false;
  bool _busy = false;
  String? _error;
  String? _notice;

  @override
  void dispose() {
    _identifier.dispose();
    _password.dispose();
    _code.dispose();
    super.dispose();
  }

  String get _verifyPath => _initialPassword
      ? '/auth/institution/initial-password/verification'
      : '/auth/institution/mfa/request';

  Future<void> _sendCode() async {
    final result = await widget.controller.api.send(
      'POST',
      _verifyPath,
      body: {'token': _challenge},
    ) as Map;
    if (!mounted) return;
    setState(
      () => _notice = result['destination'] == null
          ? 'Verification code sent.'
          : 'Verification code sent to ${result['destination']}.',
    );
  }

  Future<void> _run(Future<void> Function() action) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
      _notice = null;
    });
    try {
      await action();
    } on Object catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    await _run(() async {
      final api = widget.controller.api;
      final Map result;
      if (_challenge == null) {
        result = await api.send(
          'POST',
          '/auth/institution/login',
          body: {'email': _identifier.text.trim(), 'password': _password.text},
        ) as Map;
        if (!mounted) return;
        final initial = result['initial_password_token'] as String?;
        final challenge = initial ?? result['institution_mfa_token'] as String?;
        if (challenge != null) {
          _password.clear();
          setState(() {
            _initialPassword = initial != null;
            _challenge = challenge;
          });
          await _sendCode();
          return;
        }
      } else {
        final endpoint = _initialPassword
            ? '/auth/institution/initial-password'
            : '/auth/institution/mfa/confirm';
        result = await api.send(
          'POST',
          endpoint,
          body: {
            'token': _challenge,
            'code': _code.text.trim(),
            if (_initialPassword) 'password': _password.text,
          },
        ) as Map;
      }
      if (!mounted) return;
      await widget.controller.acceptInstitutionSession(
        result['access_token'] as String,
      );
      if (mounted) Navigator.of(context).pop();
    });
  }

  @override
  Widget build(BuildContext context) {
    final challenge = _challenge != null;
    return Scaffold(
      appBar: AppBar(title: const Text('Financial institution sign-in')),
      body: SafeArea(
        child: Form(
          key: _form,
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              if (!challenge)
                TextFormField(
                  controller: _identifier,
                  decoration: const InputDecoration(
                    labelText: 'Email or phone number',
                  ),
                  validator: (value) => value == null || value.trim().isEmpty
                      ? 'Enter your email or phone number'
                      : null,
                ),
              if (!challenge || _initialPassword)
                TextFormField(
                  controller: _password,
                  obscureText: true,
                  decoration: InputDecoration(
                    labelText: _initialPassword ? 'New password' : 'Password',
                  ),
                  validator: (value) =>
                      (value?.length ?? 0) < (_initialPassword ? 12 : 1)
                      ? _initialPassword
                            ? 'Use at least 12 characters'
                            : 'Enter your password'
                      : null,
                ),
              if (challenge) ...[
                TextFormField(
                  controller: _code,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                    labelText: 'SMS verification code',
                  ),
                  validator: (value) =>
                      RegExp(r'^\d{6}$').hasMatch(value?.trim() ?? '')
                      ? null
                      : 'Enter the six-digit code',
                ),
                TextButton(
                  onPressed: _busy ? null : () => _run(_sendCode),
                  child: const Text('Send another code'),
                ),
                TextButton(
                  onPressed: _busy
                      ? null
                      : () => setState(() {
                          _challenge = null;
                          _initialPassword = false;
                          _code.clear();
                          _password.clear();
                          _notice = null;
                          _error = null;
                        }),
                  child: const Text('Start over'),
                ),
              ],
              if (_notice != null) Text(_notice!),
              if (_error != null)
                Text(
                  _error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: _busy ? null : _submit,
                child: Text(
                  _busy
                      ? 'Please wait'
                      : challenge
                      ? 'Verify and sign in'
                      : 'Sign in',
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class InstitutionWorkspace extends StatefulWidget {
  const InstitutionWorkspace({required this.controller, super.key});

  final AppController controller;

  @override
  State<InstitutionWorkspace> createState() => _InstitutionWorkspaceState();
}

class _InstitutionWorkspaceState extends State<InstitutionWorkspace> {
  late Future<List> _memberships;

  @override
  void initState() {
    super.initState();
    _memberships = _load();
  }

  Future<List> _load() async =>
      await widget.controller.api.get('/finance/institutions/mine') as List;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('My financial institutions'),
      actions: [
        IconButton(
          tooltip: 'Sign out',
          onPressed: widget.controller.signOut,
          icon: const Icon(Icons.logout),
        ),
      ],
    ),
    body: FutureBuilder<List>(
      future: _memberships,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(snapshot.error.toString()),
                TextButton(
                  onPressed: () => setState(() => _memberships = _load()),
                  child: const Text('Try again'),
                ),
              ],
            ),
          );
        }
        if (!snapshot.hasData) {
          return const Center(child: CircularProgressIndicator());
        }
        final memberships = snapshot.data!;
        if (memberships.isEmpty) {
          return const Center(child: Text('No institution memberships found.'));
        }
        return ListView(
          children: memberships
              .map(
                (entry) => ListTile(
                  title: Text(entry['name'] as String),
                  subtitle: Text('${entry['role']} · ${entry['status']}'),
                  onTap:
                      entry['status'] == 'verified' &&
                          const [
                            'owner',
                            'officer',
                            'collections',
                          ].contains(entry['role'])
                      ? () => Navigator.of(context).push(
                          MaterialPageRoute<void>(
                            builder: (_) => _InstitutionCollections(
                              controller: widget.controller,
                              institutionId: entry['id'] as int,
                            ),
                          ),
                        )
                      : null,
                ),
              )
              .toList(),
        );
      },
    ),
  );
}

class _InstitutionCollections extends StatefulWidget {
  const _InstitutionCollections({
    required this.controller,
    required this.institutionId,
  });

  final AppController controller;
  final int institutionId;

  @override
  State<_InstitutionCollections> createState() =>
      _InstitutionCollectionsState();
}

class _InstitutionCollectionsState extends State<_InstitutionCollections> {
  final _search = TextEditingController();
  late Future<Map> _result;
  bool _customers = false;
  String _query = '';
  int _offset = 0;
  bool _syncing = false;
  String? _syncMessage;
  List<Map<String, Object?>> _queued = [];
  final _cachedCustomers = <String, Map>{};

  String get _scope =>
      '${widget.controller.apiBaseUrl}|${widget.controller.user?['id']}|${widget.institutionId}';

  Future<void> _loadQueue() async {
    if (widget.controller.user == null) return;
    final queued = await widget.controller.store.pendingCollections(_scope);
    if (mounted) setState(() => _queued = queued);
  }

  Future<void> _sync() async {
    if (_syncing) return;
    setState(() {
      _syncing = true;
      _syncMessage = null;
    });
    try {
      final count = await syncCollections(widget.controller, _scope);
      await _loadQueue();
      if (mounted) {
        setState(() {
          _syncMessage =
              '$count collections synced. ${_queued.length} still pending.';
          _result = _load();
        });
      }
    } on Object catch (error) {
      if (mounted) setState(() => _syncMessage = error.toString());
    } finally {
      if (mounted) setState(() => _syncing = false);
    }
  }

  Future<void> _playVideo(int evidenceId) async {
    final controller = widget.controller;
    try {
      await const MethodChannel(
        'aquafarm/collection-video',
      ).invokeMethod<void>('play', {
        'url':
            '${controller.apiBaseUrl}/finance/loan-evidence/$evidenceId/video',
        'token': controller.token,
      });
    } on PlatformException catch (error) {
      if (mounted) {
        setState(
          () => _syncMessage = error.message ?? 'Could not open the video.',
        );
      }
    }
  }

  Future<void> _collect(Map loan) async {
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => CollectionEntry(
          controller: widget.controller,
          scope: _scope,
          loan: loan,
        ),
      ),
    );
    if (saved == true && mounted) await _loadQueue();
  }

  @override
  void initState() {
    super.initState();
    _result = _load();
    _loadQueue();
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<Map> _load() async {
    final resource = _customers ? 'collection-customers' : 'collections';
    final cacheKey = '$_offset:$_query';
    final customers = _customers;
    try {
      final result = await widget.controller.api.send(
        'GET',
        '/finance/institutions/${widget.institutionId}/$resource',
        query: {'offset': '$_offset', if (customers) 'search': _query},
      ) as Map;
      if (customers) _cachedCustomers[cacheKey] = result;
      return result;
    } on ApiException catch (error) {
      if (error.statusCode == null &&
          customers &&
          _cachedCustomers.containsKey(cacheKey)) {
        return {..._cachedCustomers[cacheKey]!, 'offline': true};
      }
      rethrow;
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Collections'),
      actions: [
        TextButton(
          onPressed: _syncing || _queued.isEmpty ? null : _sync,
          child: Text(_syncing ? 'Syncing...' : 'Sync (${_queued.length})'),
        ),
      ],
    ),
    body: SafeArea(
      child: Column(
        children: [
          if (_syncMessage != null) Text(_syncMessage!),
          if (_queued.isNotEmpty)
            ExpansionTile(
              title: Text('${_queued.length} pending collections'),
              children: [
                for (final row in _queued)
                  ListTile(
                    title: Text(
                      "Loan #${row['loan_id']} - GHS ${row['amount']}",
                    ),
                    subtitle: Text(
                      (row['last_error'] as String?) ?? 'Waiting to sync',
                    ),
                  ),
              ],
            ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: SegmentedButton<bool>(
              segments: const [
                ButtonSegment(value: false, label: Text('Today')),
                ButtonSegment(value: true, label: Text('Customers')),
              ],
              selected: {_customers},
              onSelectionChanged: (selection) => setState(() {
                _customers = selection.single;
                _offset = 0;
                _result = _load();
              }),
            ),
          ),
          if (_customers)
            Padding(
              padding: const EdgeInsets.all(12),
              child: TextField(
                controller: _search,
                maxLength: 120,
                textInputAction: TextInputAction.search,
                decoration: const InputDecoration(
                  labelText: 'Customer or loan account number',
                ),
                onSubmitted: (value) => setState(() {
                  _query = value;
                  _offset = 0;
                  _result = _load();
                }),
              ),
            ),
          Expanded(
            child: FutureBuilder<Map>(
              future: _result,
              builder: (context, snapshot) {
                if (snapshot.connectionState != ConnectionState.done) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (snapshot.hasError) {
                  return Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(snapshot.error.toString()),
                        TextButton(
                          onPressed: () => setState(() => _result = _load()),
                          child: const Text('Try again'),
                        ),
                      ],
                    ),
                  );
                }
                final data = snapshot.data!;
                final rows = data['items'] as List;
                return ListView(
                  children: [
                    if (data['offline'] == true)
                      const ListTile(
                        title: Text('Offline ? previously loaded results'),
                      ),
                    if (!_customers)
                      ListTile(
                        title: Text(
                          "${data['count']} posted repayments - GHS ${(data['total_ghs'] as num).toStringAsFixed(2)}",
                        ),
                      ),
                    if (rows.isEmpty)
                      const ListTile(title: Text('No matching records.')),
                    for (final row in rows)
                      ListTile(
                        title: Text(row['customer_name'] as String),
                        subtitle: Text(row['account_number'] as String),
                        onTap: _customers ? () => _collect(row as Map) : null,
                        leading: !_customers && row['evidence_id'] is int
                            ? IconButton(
                                tooltip: 'Review video',
                                onPressed: () =>
                                    _playVideo(row['evidence_id'] as int),
                                icon: const Icon(Icons.play_circle_outline),
                              )
                            : null,
                        trailing: _customers
                            ? null
                            : Text(
                                'GHS ${(row['amount_ghs'] as num).toStringAsFixed(2)}',
                              ),
                      ),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        TextButton(
                          onPressed: _offset == 0
                              ? null
                              : () => setState(() {
                                  _offset -= 25;
                                  _result = _load();
                                }),
                          child: const Text('Previous'),
                        ),
                        TextButton(
                          onPressed: data['has_more'] != true
                              ? null
                              : () => setState(() {
                                  _offset += 25;
                                  _result = _load();
                                }),
                          child: const Text('Next'),
                        ),
                      ],
                    ),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    ),
  );
}
