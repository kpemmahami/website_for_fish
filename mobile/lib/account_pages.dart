import 'package:material_ui/material_ui.dart';

import 'app_controller.dart';
import 'staff_feeding_page.dart';

class PasswordRecoveryPage extends StatefulWidget {
  const PasswordRecoveryPage({
    required this.controller,
    required this.email,
    super.key,
  });

  final AppController controller;
  final String email;

  @override
  State<PasswordRecoveryPage> createState() => _PasswordRecoveryPageState();
}

class _PasswordRecoveryPageState extends State<PasswordRecoveryPage> {
  final _form = GlobalKey<FormState>();
  late final _email = TextEditingController(text: widget.email);
  bool _busy = false;
  String? _message;

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final result = await widget.controller.requestPasswordRecovery(
        _email.text,
      );
      if (mounted) setState(() => _message = result);
    } on Exception catch (error) {
      if (mounted) setState(() => _message = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Forgot password')),
    body: SafeArea(
      child: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          const Text(
            'Enter your account email. Open the reset link in your browser, then return to AquaFarm to sign in.',
          ),
          const SizedBox(height: 16),
          Form(
            key: _form,
            child: TextFormField(
              controller: _email,
              keyboardType: TextInputType.emailAddress,
              autofillHints: const [AutofillHints.email],
              decoration: const InputDecoration(labelText: 'Account email'),
              validator: (value) => value?.trim().contains('@') == true
                  ? null
                  : 'Enter your email address',
            ),
          ),
          FilledButton(
            onPressed: _busy ? null : _submit,
            child: const Text('Send reset link'),
          ),
          if (_message != null)
            Semantics(liveRegion: true, child: Text(_message!)),
        ],
      ),
    ),
  );
}

class PhoneVerificationPanel extends StatefulWidget {
  const PhoneVerificationPanel({required this.controller, super.key});

  final AppController controller;

  @override
  State<PhoneVerificationPanel> createState() => _PhoneVerificationPanelState();
}

class _PhoneVerificationPanelState extends State<PhoneVerificationPanel> {
  final _code = TextEditingController();
  String? _destination;
  String? _message;
  bool _busy = false;

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  Future<void> _request() async {
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final destination = await widget.controller.requestPhoneVerification();
      if (mounted) {
        setState(() {
          _code.clear();
          _destination = destination;
          if (destination == null) {
            _message = 'Your saved mobile number is already verified.';
          }
        });
      }
    } on Exception catch (error) {
      if (mounted) setState(() => _message = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _verify() async {
    if (!RegExp(r'^[0-9]{6}$').hasMatch(_code.text)) {
      setState(() => _message = 'Enter the six-digit SMS code.');
      return;
    }
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      await widget.controller.confirmPhoneVerification(_code.text);
      if (mounted) _code.clear();
    } on Exception catch (error) {
      if (mounted) setState(() => _message = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: widget.controller,
    builder: (context, _) {
      final account = widget.controller.user;
      if (account?['phone_verified_at'] != null) {
        return const Text('Mobile number verified.');
      }
      if (account?['phone_number'] == null) {
        return const Text(
          'No mobile number is saved. Add one in the AquaFarm web workspace.',
        );
      }
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          OutlinedButton(
            onPressed: _busy ? null : _request,
            child: Text(
              _destination == null
                  ? 'Send SMS verification code'
                  : 'Resend SMS code',
            ),
          ),
          if (_destination != null) ...[
            TextField(
              controller: _code,
              keyboardType: TextInputType.number,
              autofillHints: const [AutofillHints.oneTimeCode],
              maxLength: 6,
              decoration: InputDecoration(
                labelText: 'SMS code for $_destination',
              ),
            ),
            FilledButton(
              onPressed: _busy ? null : _verify,
              child: const Text('Verify mobile number'),
            ),
          ],
          if (_message != null)
            Semantics(liveRegion: true, child: Text(_message!)),
        ],
      );
    },
  );
}

class AssignedUnitsPage extends StatefulWidget {
  const AssignedUnitsPage({required this.controller, super.key});

  final AppController controller;

  @override
  State<AssignedUnitsPage> createState() => _AssignedUnitsPageState();
}

class _AssignedUnitsPageState extends State<AssignedUnitsPage> {
  late Future<List<Map<String, dynamic>>> _units = widget.controller
      .loadAssignedUnits();

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Assigned production units'),
      actions: [
        IconButton(
          tooltip: 'Refresh assignments',
          icon: const Icon(Icons.refresh),
          onPressed: () =>
              setState(() => _units = widget.controller.loadAssignedUnits()),
        ),
      ],
    ),
    body: FutureBuilder(
      future: _units,
      builder: (context, result) {
        if (result.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (result.hasError) {
          return Center(child: Text(result.error.toString()));
        }
        final units = result.data ?? [];
        if (units.isEmpty) {
          return const Center(child: Text('No production units assigned.'));
        }
        return ListView(
          children: [
            for (final unit in units)
              ListTile(
                title: Text(unit['unit_name'] as String),
                subtitle: Text(
                  "${unit['farm_name']} · ${unit['unit_type']} · ${unit['can_record_feeding'] == true ? 'Feeding access' : 'Read-only'}",
                ),
                trailing: unit['can_record_feeding'] == true
                    ? const Icon(Icons.chevron_right)
                    : null,
                onTap: unit['can_record_feeding'] != true
                    ? null
                    : () async {
                        final message = await Navigator.of(context)
                            .push<String>(
                              MaterialPageRoute(
                                builder: (_) => StaffFeedingPage(
                                  controller: widget.controller,
                                  assignment: unit,
                                ),
                              ),
                            );
                        if (message != null && context.mounted) {
                          ScaffoldMessenger.of(context)
                              .showSnackBar(SnackBar(content: Text(message)));
                        }
                      },
              ),
          ],
        );
      },
    ),
  );
}
