import 'package:material_ui/material_ui.dart';
import 'package:geolocator/geolocator.dart';

import 'app_controller.dart';
import 'evidence_capture.dart';
import 'offline_store.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(AquaFarmMobile(controller: AppController(OfflineStore())));
}

class AquaFarmMobile extends StatelessWidget {
  const AquaFarmMobile({required this.controller, super.key});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AquaFarm Manager Ghana',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xff146c56),
          brightness: Brightness.light,
        ),
        useMaterial3: true,
        scaffoldBackgroundColor: const Color(0xfff4f8f6),
        cardTheme: CardThemeData(
          color: Colors.white,
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(18),
            side: const BorderSide(color: Color(0xffe3ece7)),
          ),
        ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: Colors.white,
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
        ),
      ),
      home: AppBootstrap(controller: controller),
    );
  }
}

class AppBootstrap extends StatefulWidget {
  const AppBootstrap({required this.controller, super.key});

  final AppController controller;

  @override
  State<AppBootstrap> createState() => _AppBootstrapState();
}

class _AppBootstrapState extends State<AppBootstrap> {
  late final Future<void> _ready;

  @override
  void initState() {
    super.initState();
    _ready = widget.controller.initialize();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<void>(
      future: _ready,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }
        return AnimatedBuilder(
          animation: widget.controller,
          builder: (context, _) => widget.controller.user == null
              ? LoginPage(controller: widget.controller)
              : widget.controller.user?['account_type'] == 'pending_farmer'
                  ? ApprovalPendingPage(controller: widget.controller)
                  : MobileHome(controller: widget.controller),
        );
      },
    );
  }
}

class ApprovalPendingPage extends StatelessWidget {
  const ApprovalPendingPage({required this.controller, super.key});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('Account pending approval', style: Theme.of(context).textTheme.headlineSmall),
                const Text('An AquaFarm administrator needs to approve your account.'),
                if (controller.error != null) Text(controller.error!),
                FilledButton(
                  onPressed: controller.loading ? null : controller.checkApproval,
                  child: const Text('Check approval status'),
                ),
                TextButton(onPressed: controller.signOut, child: const Text('Sign out')),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class LoginPage extends StatefulWidget {
  const LoginPage({required this.controller, super.key});

  final AppController controller;

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _phone = TextEditingController();
  final _password = TextEditingController();
  bool _register = false;
  bool _showPassword = false;

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _phone.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    if (_register) {
      await widget.controller.registerAndAuthenticate(
        fullName: _name.text,
        email: _email.text,
        phoneNumber: _phone.text,
        password: _password.text,
      );
    } else {
      await widget.controller.authenticate(_email.text, _password.text);
    }
  }

  Future<void> _configureApi() async {
    final address = TextEditingController(text: widget.controller.apiBaseUrl);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Backend address'),
        content: TextField(
          controller: address,
          keyboardType: TextInputType.url,
          decoration: const InputDecoration(
            labelText: 'API URL',
            hintText: 'http://10.0.2.2:8000',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (confirmed == true && mounted) {
      try {
        await widget.controller.configureApiUrl(address.text);
      } on Object catch (error) {
        if (mounted) {
          ScaffoldMessenger.of(context)
              .showSnackBar(SnackBar(content: Text(error.toString())));
        }
      }
    }
    address.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 460),
              child: Card(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Form(
                    key: _formKey,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Icon(Icons.waves, size: 44, color: Color(0xff146c56)),
                        const SizedBox(height: 10),
                        Text(
                          'AquaFarm Manager',
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                                fontWeight: FontWeight.w800,
                              ),
                        ),
                        const Text(
                          'Ghana · Farm operations',
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 24),
                        if (_register)
                          TextFormField(
                            controller: _name,
                            textCapitalization: TextCapitalization.words,
                            decoration: const InputDecoration(labelText: 'Full name'),
                            validator: (value) => (value?.trim().length ?? 0) < 2
                                ? 'Enter your name'
                                : null,
                          ),
                        if (_register) const SizedBox(height: 12),
                        TextFormField(
                          controller: _email,
                          keyboardType: _register ? TextInputType.emailAddress : TextInputType.text,
                          autofillHints: [_register ? AutofillHints.email : AutofillHints.username],
                          decoration: InputDecoration(labelText: _register ? 'Email' : 'Email or phone number'),
                          validator: (value) => (value?.trim().isEmpty ?? true)
                              ? 'Enter your email or phone number'
                              : _register && !value!.contains('@') ? 'Enter a valid email' : null,
                        ),
                        if (_register) ...[
                          const SizedBox(height: 12),
                          TextFormField(
                            controller: _phone,
                            keyboardType: TextInputType.phone,
                            autofillHints: const [AutofillHints.telephoneNumber],
                            decoration: const InputDecoration(labelText: 'Mobile phone number'),
                            validator: (value) => (value?.trim().isEmpty ?? true)
                                ? 'Enter your mobile phone number'
                                : null,
                          ),
                        ],
                        const SizedBox(height: 12),
                        TextFormField(
                          controller: _password,
                          obscureText: !_showPassword,
                          autofillHints: [
                            _register ? AutofillHints.newPassword : AutofillHints.password,
                          ],
                          decoration: InputDecoration(
                            labelText: 'Password',
                            helperText: _register ? 'At least 12 characters' : null,
                            suffixIcon: IconButton(
                              onPressed: () => setState(() => _showPassword = !_showPassword),
                              icon: Icon(_showPassword ? Icons.visibility_off : Icons.visibility),
                            ),
                          ),
                          validator: (value) => value == null ||
                                  value.length < (_register ? 12 : 1)
                              ? _register
                                  ? 'Use at least 12 characters'
                                  : 'Enter your password'
                              : null,
                        ),
                        if (controller.error != null) ...[
                          const SizedBox(height: 12),
                          _MessageCard(message: controller.error!, isError: true),
                        ],
                        const SizedBox(height: 18),
                        FilledButton(
                          onPressed: controller.loading ? null : _submit,
                          child: controller.loading
                              ? const SizedBox(
                                  width: 20,
                                  height: 20,
                                  child: CircularProgressIndicator(strokeWidth: 2),
                                )
                              : Text(_register ? 'Create account' : 'Sign in'),
                        ),
                        TextButton(
                          onPressed: () => setState(() {
                            _register = !_register;
                            controller.error = null;
                          }),
                          child: Text(_register
                              ? 'Already have an account? Sign in'
                              : 'New to AquaFarm? Create an account'),
                        ),
                        const Divider(),
                        Text(
                          'API: ${controller.apiBaseUrl}',
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                        TextButton.icon(
                          onPressed: _configureApi,
                          icon: const Icon(Icons.settings_ethernet),
                          label: const Text('Change backend address'),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class MobileHome extends StatefulWidget {
  const MobileHome({required this.controller, super.key});

  final AppController controller;

  @override
  State<MobileHome> createState() => _MobileHomeState();
}

class _MobileHomeState extends State<MobileHome> {
  int _index = 0;

  Future<void> _showSettings() async {
    final address = TextEditingController(text: widget.controller.apiBaseUrl);
    final result = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      builder: (context) => Padding(
        padding: EdgeInsets.fromLTRB(
          20,
          24,
          20,
          MediaQuery.viewInsetsOf(context).bottom + 24,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Settings', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 16),
            TextField(
              controller: address,
              keyboardType: TextInputType.url,
              decoration: const InputDecoration(
                labelText: 'Backend API URL',
                helperText: 'Emulator default: http://10.0.2.2:8000',
              ),
            ),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: () => Navigator.pop(context, address.text),
              child: const Text('Save backend address'),
            ),
            OutlinedButton.icon(
              onPressed: () => Navigator.pop(context, ''),
              icon: const Icon(Icons.logout),
              label: const Text('Sign out'),
            ),
          ],
        ),
      ),
    );
    address.dispose();
    if (!mounted || result == null) return;
    try {
      if (result.isEmpty) {
        await widget.controller.signOut();
      } else {
        await widget.controller.configureApiUrl(result);
      }
    } on Object catch (error) {
      _showMessage(error.toString(), isError: true);
    }
  }

  void _showMessage(String message, {bool isError = false}) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      backgroundColor: isError ? Theme.of(context).colorScheme.error : null,
      content: Text(message),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    final pages = [
      DashboardPage(controller: controller, onOpenFarms: () => setState(() => _index = 1)),
      FarmsPage(controller: controller),
      OperationsPage(controller: controller),
      ReportsPage(controller: controller),
    ];
    return Scaffold(
      appBar: AppBar(
        title: const Text('AquaFarm'),
        actions: [
          if (controller.farms.length > 1)
            PopupMenuButton<int>(
              tooltip: 'Change farm',
              icon: const Icon(Icons.agriculture),
              onSelected: (id) => controller.selectFarm(id),
              itemBuilder: (context) => controller.farms
                  .map((farm) => PopupMenuItem<int>(
                        value: farm['id'] as int,
                        child: Text(farm['name'] as String),
                      ))
                  .toList(),
            ),
          IconButton(
            tooltip: 'Sync pending records',
            onPressed: controller.syncing
                ? null
                : () => controller.syncPending(),
            icon: controller.syncing
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : Badge(
                    isLabelVisible: controller.pendingCount > 0,
                    label: Text('${controller.pendingCount}'),
                    child: const Icon(Icons.sync),
                  ),
          ),
          IconButton(
            tooltip: 'Settings',
            onPressed: _showSettings,
            icon: const Icon(Icons.settings_outlined),
          ),
        ],
      ),
      body: Column(
        children: [
          if (controller.error != null || controller.notice != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
              child: _MessageCard(
                message: controller.error ?? controller.notice!,
                isError: controller.error != null,
                onDismiss: () {
                  controller.clearMessages();
                },
              ),
            ),
          if (controller.pendingCount > 0)
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
              child: Card(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '${controller.pendingCount} record${controller.pendingCount == 1 ? '' : 's'} waiting to sync',
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                      const SizedBox(height: 4),
                      const Text(
                        'Offline records and videos are saved on this device until upload succeeds.',
                      ),
                      Wrap(
                        spacing: 8,
                        children: [
                          TextButton.icon(
                            onPressed: controller.syncing
                                ? null
                                : () => controller.syncPending(),
                            icon: const Icon(Icons.sync),
                            label: const Text('Sync now'),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ),
          if (controller.selectedFarm != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
              child: Card(
                child: ListTile(
                  leading: const Icon(Icons.offline_bolt_outlined),
                  title: const Text('Prepare for offline work'),
                  subtitle: const Text(
                    'Cache one-time activity codes for this farm’s units before going offline.',
                  ),
                  trailing: TextButton(
                    onPressed: () async {
                      try {
                        await controller.prepareOfflineCodes();
                      } on Object catch (error) {
                        _showMessage(error.toString(), isError: true);
                      }
                    },
                    child: const Text('Prepare'),
                  ),
                ),
              ),
            ),
          Expanded(
            child: controller.loading
                ? const Center(child: CircularProgressIndicator())
                : IndexedStack(index: _index, children: pages),
          ),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (value) => setState(() => _index = value),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.dashboard_outlined), label: 'Overview'),
          NavigationDestination(icon: Icon(Icons.agriculture_outlined), label: 'Farms'),
          NavigationDestination(icon: Icon(Icons.set_meal_outlined), label: 'Operations'),
          NavigationDestination(icon: Icon(Icons.assessment_outlined), label: 'Reports'),
        ],
      ),
    );
  }
}

class DashboardPage extends StatelessWidget {
  const DashboardPage({
    required this.controller,
    required this.onOpenFarms,
    super.key,
  });

  final AppController controller;
  final VoidCallback onOpenFarms;

  @override
  Widget build(BuildContext context) {
    final farm = controller.selectedFarm;
    final summary = controller.analytics?['summary'] as Map? ?? {};
    if (farm == null) {
      return _EmptyState(
        icon: Icons.agriculture,
        title: 'Register your first farm',
        message: 'Add a farm and GPS location to start recording production.',
        action: FilledButton(onPressed: onOpenFarms, child: const Text('Open farms')),
      );
    }
    return RefreshIndicator(
      onRefresh: controller.refresh,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(farm['name'] as String, style: Theme.of(context).textTheme.headlineSmall),
          Text('${farm['district']}, ${farm['region']} · ${farm['species']}'),
          const SizedBox(height: 16),
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            childAspectRatio: 1.55,
            crossAxisSpacing: 10,
            mainAxisSpacing: 10,
            children: [
              _MetricCard(label: 'Active cycles', value: '${summary['active_cycles'] ?? 0}', icon: Icons.water),
              _MetricCard(label: 'Live fish estimate', value: _format(summary['estimated_live_fish']), icon: Icons.set_meal),
              _MetricCard(label: 'Estimated biomass', value: '${_format(summary['estimated_biomass_kg'])} kg', icon: Icons.scale),
              _MetricCard(
                label: 'Feed remaining',
                value: '${_format(summary['remaining_feed_kg'])} kg',
                icon: Icons.inventory_2_outlined,
              ),
            ],
          ),
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Production units', style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 8),
                  if (controller.units.isEmpty)
                    const Text('No units registered for this farm.')
                  else
                    ...controller.units.map((unit) {
                      final unitCycles = controller.cycles
                          .where((cycle) => cycle['unit_id'] == unit['id'] &&
                              cycle['closed_at'] == null)
                          .length;
                      return ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: const Icon(Icons.water),
                        title: Text(unit['name'] as String),
                        subtitle: Text('${unit['unit_type']} · $unitCycles active cycle(s)'),
                      );
                    }),
                ],
              ),
            ),
          ),
          const Padding(
            padding: EdgeInsets.all(8),
            child: Text(
              'Fish counts, biomass and forecasts are record-derived estimates.',
              textAlign: TextAlign.center,
            ),
          ),
        ],
      ),
    );
  }
}

class FarmsPage extends StatelessWidget {
  const FarmsPage({required this.controller, super.key});

  final AppController controller;

  Future<void> _addFarm(BuildContext context) async {
    final farm = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (_) => const FarmFormDialog(),
    );
    if (farm == null || !context.mounted) return;
    try {
      await controller.createFarm(farm);
    } on Object catch (error) {
      if (context.mounted) {
        _snack(context, error.toString(), isError: true);
      }
    }
  }

  Future<void> _addUnit(BuildContext context) async {
    final unit = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (_) => const UnitFormDialog(),
    );
    if (unit == null || !context.mounted) return;
    try {
      await controller.createUnit(unit);
    } on Object catch (error) {
      if (context.mounted) {
        _snack(context, error.toString(), isError: true);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final farm = controller.selectedFarm;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Row(
          children: [
            Expanded(child: Text('My farms', style: Theme.of(context).textTheme.headlineSmall)),
            IconButton.filledTonal(
              tooltip: 'Register a farm',
              onPressed: () => _addFarm(context),
              icon: const Icon(Icons.add),
            ),
          ],
        ),
        if (controller.farms.isEmpty)
          const Card(
            child: Padding(
              padding: EdgeInsets.all(18),
              child: Text('No farms yet. Add a farm and capture its GPS location.'),
            ),
          )
        else
          ...controller.farms.map((item) => Card(
                child: ListTile(
                  leading: const CircleAvatar(child: Icon(Icons.agriculture)),
                  title: Text(item['name'] as String),
                  subtitle: Text(
                    '${item['district']}, ${item['region']} · ${item['species']}',
                  ),
                  trailing: item['id'] == controller.selectedFarmId
                      ? const Icon(Icons.check_circle, color: Color(0xff146c56))
                      : const Icon(Icons.chevron_right),
                  onTap: () => controller.selectFarm(item['id'] as int),
                ),
              )),
        if (farm != null) ...[
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: Text(
                  'Units · ${farm['name']}',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ),
              IconButton.filledTonal(
                tooltip: 'Add production unit',
                onPressed: () => _addUnit(context),
                icon: const Icon(Icons.add),
              ),
            ],
          ),
          if (controller.units.isEmpty)
            const Card(
              child: Padding(
                padding: EdgeInsets.all(18),
                child: Text('Add a pond, tank or cage to begin tracking fish.'),
              ),
            )
          else
            ...controller.units.map((unit) => Card(
                  child: ListTile(
                    leading: const Icon(Icons.water),
                    title: Text(unit['name'] as String),
                    subtitle: Text(
                      '${unit['unit_type']} · Evidence tag ${unit['evidence_tag'] ?? 'not assigned'}',
                    ),
                  ),
                )),
        ],
      ],
    );
  }
}

class OperationsPage extends StatefulWidget {
  const OperationsPage({required this.controller, super.key});

  final AppController controller;

  @override
  State<OperationsPage> createState() => _OperationsPageState();
}

class _OperationsPageState extends State<OperationsPage> {
  int? _unitId;
  int? _cycleId;
  String? _busyActivity;

  @override
  void didUpdateWidget(covariant OperationsPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.controller.selectedFarmId != widget.controller.selectedFarmId) {
      _unitId = null;
      _cycleId = null;
    }
  }

  Map<String, dynamic>? get _unit {
    final selectedId = _effectiveUnitId;
    for (final item in widget.controller.units) {
      if (item['id'] == selectedId) return item;
    }
    return null;
  }

  int? get _effectiveUnitId {
    if (widget.controller.units.any((item) => item['id'] == _unitId)) {
      return _unitId;
    }
    return widget.controller.units.isEmpty
        ? null
        : widget.controller.units.first['id'] as int;
  }

  List<Map<String, dynamic>> get _unitCycles => widget.controller.activeCycles
      .where((cycle) => cycle['unit_id'] == _effectiveUnitId)
      .toList();

  Map<String, dynamic>? get _cycle {
    for (final item in _unitCycles) {
      if (item['id'] == _cycleId) return item;
    }
    return _unitCycles.isEmpty ? null : _unitCycles.first;
  }

  Future<void> _record(String activity) async {
    final unit = _unit;
    final farm = widget.controller.selectedFarm;
    if (unit == null || farm == null) return;
    if (activity != 'stocking' && _cycle == null) {
      _snack(context, 'Stock fingerlings before recording this activity.', isError: true);
      return;
    }
    final body = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (_) => OperationFormDialog(
        activity: activity,
        farm: farm,
        feeds: widget.controller.feeds,
      ),
    );
    if (body == null || !mounted) return;
    setState(() => _busyActivity = activity);
    try {
      final evidence = await Navigator.of(context).push<EvidenceCapture>(
        MaterialPageRoute(
          builder: (_) => EvidenceCapturePage(
            api: widget.controller.api,
            store: widget.controller.store,
            ownerId: widget.controller.user!['id'] as int,
            farm: farm,
            unit: unit,
            activity: activity,
            cycleId: activity == 'stocking' ? null : _cycle!['id'] as int,
          ),
        ),
      );
      if (evidence == null || !mounted) return;
      await widget.controller.queueOperation(
        activity: activity,
        unit: unit,
        cycleId: activity == 'stocking' ? null : _cycle!['id'] as int,
        body: body,
        evidence: evidence,
      );
    } on Object catch (error) {
      if (mounted) _snack(context, error.toString(), isError: true);
    } finally {
      if (mounted) setState(() => _busyActivity = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    if (controller.selectedFarm == null) {
      return const _EmptyState(
        icon: Icons.agriculture,
        title: 'Select or register a farm',
        message: 'Production operations belong to a farm.',
      );
    }
    if (controller.units.isEmpty) {
      return const _EmptyState(
        icon: Icons.water,
        title: 'Add a production unit',
        message: 'Create a pond, cage or tank in the Farms tab first.',
      );
    }
    final cycle = _cycle;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Daily operations', style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: 12),
        DropdownButtonFormField<int>(
          initialValue: _effectiveUnitId,
          decoration: const InputDecoration(labelText: 'Production unit'),
          items: controller.units
              .map((unit) => DropdownMenuItem<int>(
                    value: unit['id'] as int,
                    child: Text(unit['name'] as String),
                  ))
              .toList(),
          onChanged: (id) => setState(() {
            _unitId = id;
            _cycleId = null;
          }),
        ),
        const SizedBox(height: 10),
        if (_unitCycles.isNotEmpty)
          DropdownButtonFormField<int>(
            initialValue: _unitCycles.any((item) => item['id'] == _cycleId)
                ? _cycleId
                : _unitCycles.first['id'] as int,
            decoration: const InputDecoration(labelText: 'Active production cycle'),
            items: _unitCycles
                .map((item) => DropdownMenuItem<int>(
                      value: item['id'] as int,
                      child: Text('${item['species']} · stocked ${item['stocked_on']}'),
                    ))
                .toList(),
            onChanged: (id) => setState(() => _cycleId = id),
          ),
        if (cycle != null) ...[
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Text(
                '${cycle['species']} · ${cycle['stocked_count']} fingerlings · '
                'initial average ${_format(cycle['initial_average_weight_g'])} g',
              ),
            ),
          ),
        ],
        const SizedBox(height: 10),
        _ActionTile(
          title: 'Stock fingerlings',
          subtitle: 'Record supplier, quantity and initial average weight.',
          icon: Icons.add_circle_outline,
          busy: _busyActivity == 'stocking',
          disabled: _unitCycles.isNotEmpty,
          onTap: () => _record('stocking'),
        ),
        _ActionTile(
          title: 'Record feeding',
          subtitle: 'Log feed type, quantity and date; stock is reconciled by the API.',
          icon: Icons.restaurant,
          busy: _busyActivity == 'feeding',
          onTap: () => _record('feeding'),
        ),
        _ActionTile(
          title: 'Record mortality',
          subtitle: 'Update estimated fish population.',
          icon: Icons.warning_amber,
          busy: _busyActivity == 'mortality',
          onTap: () => _record('mortality'),
        ),
        _ActionTile(
          title: 'Record fish sample',
          subtitle: 'Enter individual weights; the average is calculated automatically.',
          icon: Icons.scale,
          busy: _busyActivity == 'growth',
          onTap: () => _record('growth'),
        ),
        _ActionTile(
          title: 'Record water quality',
          subtitle: 'Temperature, dissolved oxygen, pH, ammonia or nitrite.',
          icon: Icons.water_drop_outlined,
          busy: _busyActivity == 'water_quality',
          onTap: () => _record('water_quality'),
        ),
        const SizedBox(height: 8),
        const _InfoCard(
          text: 'Every operation requires a new 15-second in-app video and a GPS reading. '
              'Records are saved locally and queued when the API is unavailable.',
        ),
      ],
    );
  }
}

class ReportsPage extends StatelessWidget {
  const ReportsPage({required this.controller, super.key});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    final analytics = controller.analytics;
    if (controller.selectedFarm == null || analytics == null) {
      return const _EmptyState(
        icon: Icons.assessment_outlined,
        title: 'No farm report yet',
        message: 'Register or select a farm to see generated production and financial indicators.',
      );
    }
    final summary = analytics['summary'] as Map? ?? {};
    final production = analytics['production'] as Map? ?? {};
    final finance = analytics['finance'] as Map? ?? {};
    final pricing = (finance['pricing_by_plan'] as List? ?? const [])
        .cast<Map>();
    final forecasts = (production['harvest_forecasts'] as List? ?? const [])
        .cast<Map>();
    return RefreshIndicator(
      onRefresh: controller.refresh,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('Farm reports', style: Theme.of(context).textTheme.headlineSmall),
          Text('Generated from records for ${controller.selectedFarm!['name']}'),
          const SizedBox(height: 12),
          _MetricCard(
            label: 'Estimated harvest',
            value: summary['expected_harvest_kg'] == null
                ? 'Unavailable'
                : '${_format(summary['expected_harvest_kg'])} kg',
            icon: Icons.trending_up,
          ),
          _MetricCard(
            label: 'Recorded costs to date',
            value: _money(summary['recorded_costs_to_date_ghs']),
            icon: Icons.payments_outlined,
          ),
          const SizedBox(height: 12),
          Text('Harvest forecasts', style: Theme.of(context).textTheme.titleLarge),
          if (forecasts.isEmpty)
            const _InfoCard(text: 'No active cycles have a linked production plan.')
          else
            ...forecasts.map((item) => Card(
                  child: ListTile(
                    title: Text('${item['unit_name']} · ${item['species']}'),
                    subtitle: Text(
                      '${item['expected_harvest_kg'] == null ? 'No weight estimate' : '${_format(item['expected_harvest_kg'])} kg'}'
                      ' · date ${item['expected_harvest_on'] ?? 'unavailable'}',
                    ),
                  ),
                )),
          const SizedBox(height: 12),
          Text('Cost and pricing estimates', style: Theme.of(context).textTheme.titleLarge),
          if (pricing.isEmpty)
            const _InfoCard(text: 'No production plans are recorded yet.')
          else
            ...pricing.map((item) => Card(
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Plan #${item['plan_id']} · ${item['species']}',
                            style: const TextStyle(fontWeight: FontWeight.w700)),
                        const SizedBox(height: 8),
                        Text('Projected cost ${_money(item['projected_cycle_total_cost_ghs'])}'),
                        Text('Break-even ${_money(item['break_even_ghs_per_kg'])}/kg'),
                        Text('Recommended ${_money(item['recommended_price_ghs_per_kg'])}/kg'),
                        Text('Projected revenue ${_money(item['projected_revenue_ghs'])}'),
                        Text('Projected profit ${_money(item['projected_profit_ghs'])}'),
                        if (item['market_price_ghs_per_kg'] != null)
                          Text('Market comparison ${_money(item['market_price_ghs_per_kg'])}/kg'),
                      ],
                    ),
                  ),
                )),
          const SizedBox(height: 8),
          const _InfoCard(
            text: 'Biomass, costs, harvest, revenue and profit are estimates from recorded data, '
                'not audited or independently verified statements.',
          ),
        ],
      ),
    );
  }
}

class FarmFormDialog extends StatefulWidget {
  const FarmFormDialog({super.key});

  @override
  State<FarmFormDialog> createState() => _FarmFormDialogState();
}

class _FarmFormDialogState extends State<FarmFormDialog> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _region = TextEditingController();
  final _district = TextEditingController();
  final _species = TextEditingController(text: 'Tilapia');
  final _latitude = TextEditingController();
  final _longitude = TextEditingController();
  String _farmType = 'pond';
  bool _capturedByGps = false;
  double? _accuracy;
  String? _locationError;
  bool _locating = false;

  @override
  void dispose() {
    _name.dispose();
    _region.dispose();
    _district.dispose();
    _species.dispose();
    _latitude.dispose();
    _longitude.dispose();
    super.dispose();
  }

  Future<void> _captureGps() async {
    setState(() {
      _locating = true;
      _locationError = null;
    });
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        throw Exception('Turn on device location services.');
      }
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        throw Exception('Location permission is required to capture farm GPS.');
      }
      final location = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 25),
        ),
      );
      _latitude.text = location.latitude.toStringAsFixed(7);
      _longitude.text = location.longitude.toStringAsFixed(7);
      _accuracy = location.accuracy;
      _capturedByGps = true;
    } on Object catch (error) {
      _locationError = error.toString();
    } finally {
      if (mounted) setState(() => _locating = false);
    }
  }

  String? _required(String? value) =>
      value == null || value.trim().length < 2 ? 'Required' : null;

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Register farm'),
      content: SizedBox(
        width: 480,
        child: Form(
          key: _formKey,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextFormField(controller: _name, decoration: const InputDecoration(labelText: 'Farm name'), validator: _required),
                const SizedBox(height: 10),
                TextFormField(controller: _region, decoration: const InputDecoration(labelText: 'Region'), validator: _required),
                const SizedBox(height: 10),
                TextFormField(controller: _district, decoration: const InputDecoration(labelText: 'District'), validator: _required),
                const SizedBox(height: 10),
                DropdownButtonFormField<String>(
                  initialValue: _farmType,
                  decoration: const InputDecoration(labelText: 'Farm type'),
                  items: const [
                    DropdownMenuItem(value: 'pond', child: Text('Pond')),
                    DropdownMenuItem(value: 'cage', child: Text('Cage')),
                    DropdownMenuItem(value: 'tank', child: Text('Tank')),
                    DropdownMenuItem(value: 'mixed', child: Text('Mixed')),
                  ],
                  onChanged: (value) => setState(() => _farmType = value ?? 'pond'),
                ),
                const SizedBox(height: 10),
                TextFormField(controller: _species, decoration: const InputDecoration(labelText: 'Primary species'), validator: _required),
                const SizedBox(height: 14),
                OutlinedButton.icon(
                  onPressed: _locating ? null : _captureGps,
                  icon: const Icon(Icons.my_location),
                  label: Text(_locating ? 'Getting GPS…' : 'Capture farm GPS'),
                ),
                if (_locationError != null)
                  Text(_locationError!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                Row(
                  children: [
                    Expanded(
                      child: TextFormField(
                        controller: _latitude,
                        keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
                        decoration: const InputDecoration(labelText: 'Latitude'),
                        onChanged: (_) => _capturedByGps = false,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: TextFormField(
                        controller: _longitude,
                        keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
                        decoration: const InputDecoration(labelText: 'Longitude'),
                        onChanged: (_) => _capturedByGps = false,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                const Text('GPS is needed to verify operation videos against the farm location.'),
              ],
            ),
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(
          onPressed: () {
            if (!_formKey.currentState!.validate()) return;
            final latitude = double.tryParse(_latitude.text);
            final longitude = double.tryParse(_longitude.text);
            if ((latitude == null) != (longitude == null)) {
              setState(() => _locationError = 'Enter both coordinates or leave both blank.');
              return;
            }
            final body = <String, dynamic>{
              'name': _name.text.trim(),
              'region': _region.text.trim(),
              'district': _district.text.trim(),
              'farm_type': _farmType,
              'species': _species.text.trim(),
            };
            if (latitude != null && longitude != null) {
              body['latitude'] = latitude;
              body['longitude'] = longitude;
              body['location_method'] = _capturedByGps ? 'gps' : 'manual';
              if (_capturedByGps) {
                body['gps_accuracy_m'] = _accuracy;
                body['gps_captured_at'] = DateTime.now().toUtc().toIso8601String();
              }
            }
            Navigator.pop(context, body);
          },
          child: const Text('Save farm'),
        ),
      ],
    );
  }
}

class UnitFormDialog extends StatefulWidget {
  const UnitFormDialog({super.key});

  @override
  State<UnitFormDialog> createState() => _UnitFormDialogState();
}

class _UnitFormDialogState extends State<UnitFormDialog> {
  final _formKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _capacity = TextEditingController();
  String _type = 'pond';

  @override
  void dispose() {
    _name.dispose();
    _capacity.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Add production unit'),
      content: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextFormField(
              controller: _name,
              decoration: const InputDecoration(labelText: 'Unit name'),
              validator: (value) => value == null || value.trim().length < 2 ? 'Required' : null,
            ),
            const SizedBox(height: 10),
            DropdownButtonFormField<String>(
              initialValue: _type,
              decoration: const InputDecoration(labelText: 'Unit type'),
              items: const [
                DropdownMenuItem(value: 'pond', child: Text('Pond')),
                DropdownMenuItem(value: 'cage', child: Text('Cage')),
                DropdownMenuItem(value: 'tank', child: Text('Tank')),
              ],
              onChanged: (value) => setState(() => _type = value ?? 'pond'),
            ),
            const SizedBox(height: 10),
            TextFormField(
              controller: _capacity,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(labelText: 'Capacity (m³, optional)'),
              validator: (value) {
                if (value == null || value.isEmpty) return null;
                final number = double.tryParse(value);
                return number == null || number <= 0 ? 'Enter a positive capacity' : null;
              },
            ),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(
          onPressed: () {
            if (!_formKey.currentState!.validate()) return;
            Navigator.pop(context, {
              'name': _name.text.trim(),
              'unit_type': _type,
              'capacity_m3': double.tryParse(_capacity.text),
            });
          },
          child: const Text('Save unit'),
        ),
      ],
    );
  }
}

class OperationFormDialog extends StatefulWidget {
  const OperationFormDialog({
    required this.activity,
    required this.farm,
    required this.feeds,
    super.key,
  });

  final String activity;
  final Map<String, dynamic> farm;
  final List<Map<String, dynamic>> feeds;

  @override
  State<OperationFormDialog> createState() => _OperationFormDialogState();
}

class _OperationFormDialogState extends State<OperationFormDialog> {
  final _formKey = GlobalKey<FormState>();
  final Map<String, TextEditingController> _fields = {};
  int? _feedId;
  String? _error;

  String _value(String key, [String fallback = '']) =>
      _fields.putIfAbsent(key, () => TextEditingController(text: fallback)).text.trim();

  TextFormField _field(
    String key,
    String label, {
    bool required = true,
    bool decimal = false,
    String? initial,
    TextInputType? keyboardType,
    bool numeric = true,
  }) {
    final controller = _fields.putIfAbsent(
      key,
      () => TextEditingController(text: initial ?? ''),
    );
    return TextFormField(
      controller: controller,
      keyboardType: keyboardType ??
          (decimal
              ? const TextInputType.numberWithOptions(decimal: true)
              : TextInputType.number),
      decoration: InputDecoration(labelText: label),
      validator: (value) {
        if ((value == null || value.trim().isEmpty) && required) return 'Required';
        if (value == null || value.trim().isEmpty) return null;
        if (numeric &&
            (decimal ? double.tryParse(value) == null : int.tryParse(value) == null)) {
          return 'Enter a valid number';
        }
        if (numeric) {
          final number = decimal ? double.parse(value) : int.parse(value);
          if (!number.isFinite || number <= 0) return 'Enter a value greater than zero';
        }
        return null;
      },
    );
  }

  @override
  void dispose() {
    for (final controller in _fields.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Map<String, dynamic>? _buildBody() {
    if (!_formKey.currentState!.validate()) return null;
    final today = DateTime.now().toIso8601String().substring(0, 10);
    final notes = _value('notes');
    switch (widget.activity) {
      case 'stocking':
        return {
          'species': _value('species'),
          'stocked_count': int.parse(_value('stocked_count')),
          'initial_average_weight_g': double.parse(_value('initial_average_weight_g')),
          'fingerling_supplier': _value('fingerling_supplier').isEmpty
              ? null
              : _value('fingerling_supplier'),
          'stocked_on': _value('stocked_on', today),
          'notes': notes.isEmpty ? null : notes,
        };
      case 'mortality':
        return {
          'dead_count': int.parse(_value('dead_count')),
          'observed_on': _value('observed_on', today),
          'cause': _value('cause').isEmpty ? null : _value('cause'),
          'notes': notes.isEmpty ? null : notes,
        };
      case 'growth':
        final weights = <double>[];
        for (final value in _value('weights_g').split(RegExp(r'[,;\s]+'))) {
          if (value.isEmpty) continue;
          final weight = double.tryParse(value);
          if (weight == null) {
            setState(() => _error = 'Enter numeric fish weights separated by spaces or commas.');
            return null;
          }
          weights.add(weight);
        }
        if (weights.isEmpty || weights.any((weight) => !weight.isFinite || weight <= 0)) {
          setState(() => _error = 'Enter one or more positive fish weights in grams.');
          return null;
        }
        return {
          'sampled_on': _value('sampled_on', today),
          'weights_g': weights,
          'notes': notes.isEmpty ? null : notes,
        };
      case 'water_quality':
        final body = <String, dynamic>{
          'observed_at': DateTime.now().toUtc().toIso8601String(),
          'notes': notes.isEmpty ? null : notes,
        };
        for (final key in [
          'temperature_c',
          'dissolved_oxygen_mg_l',
          'ph',
          'ammonia_mg_l',
          'nitrite_mg_l',
        ]) {
          final value = _value(key);
          if (value.isNotEmpty) {
            final reading = double.tryParse(value);
            if (reading == null || !reading.isFinite) {
              setState(() => _error = 'Enter valid finite water-quality measurements.');
              return null;
            }
            body[key] = reading;
          }
        }
        if (body.length <= 2) {
          setState(() => _error = 'Enter at least one water-quality measurement.');
          return null;
        }
        return body;
      case 'feeding':
        if (_feedId == null) {
          setState(() => _error = 'Select a feed product.');
          return null;
        }
        return {
          'feed_id': _feedId,
          'quantity_kg': double.parse(_value('quantity_kg')),
          'fed_on': _value('fed_on', today),
          'notes': notes.isEmpty ? null : notes,
        };
      default:
        return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    final title = switch (widget.activity) {
      'stocking' => 'Stock fingerlings',
      'mortality' => 'Record mortality',
      'growth' => 'Record fish sample',
      'water_quality' => 'Record water quality',
      'feeding' => 'Record feeding',
      _ => 'Record operation',
    };
    final today = DateTime.now().toIso8601String().substring(0, 10);
    final fields = <Widget>[];
    switch (widget.activity) {
      case 'stocking':
        fields.addAll([
          _field('species', 'Species', initial: widget.farm['species'] as String? ?? 'Tilapia', keyboardType: TextInputType.text, numeric: false),
          _field('stocked_count', 'Fingerling quantity'),
          _field('initial_average_weight_g', 'Initial average weight (g)', decimal: true),
          _field('fingerling_supplier', 'Supplier (optional)', required: false, keyboardType: TextInputType.text, numeric: false),
          _field('stocked_on', 'Stocking date (YYYY-MM-DD)', initial: today, keyboardType: TextInputType.datetime, numeric: false),
        ]);
        break;
      case 'mortality':
        fields.addAll([
          _field('dead_count', 'Number of fish dead'),
          _field('cause', 'Suspected cause (optional)', required: false, keyboardType: TextInputType.text, numeric: false),
          _field('observed_on', 'Date (YYYY-MM-DD)', initial: today, keyboardType: TextInputType.datetime, numeric: false),
        ]);
        break;
      case 'growth':
        fields.addAll([
          _field('weights_g', 'Individual sample weights (g)', keyboardType: TextInputType.text, numeric: false),
          _field('sampled_on', 'Sample date (YYYY-MM-DD)', initial: today, keyboardType: TextInputType.datetime, numeric: false),
          const Padding(
            padding: EdgeInsets.only(top: 6),
            child: Text('Separate weights with spaces or commas.'),
          ),
        ]);
        break;
      case 'water_quality':
        fields.addAll([
          _field('temperature_c', 'Temperature (°C)', required: false, decimal: true),
          _field('dissolved_oxygen_mg_l', 'Dissolved oxygen (mg/L)', required: false, decimal: true),
          _field('ph', 'pH', required: false, decimal: true),
          _field('ammonia_mg_l', 'Ammonia (mg/L)', required: false, decimal: true),
          _field('nitrite_mg_l', 'Nitrite (mg/L)', required: false, decimal: true),
        ]);
        break;
      case 'feeding':
        if (widget.feeds.isNotEmpty) _feedId ??= widget.feeds.first['id'] as int;
        fields.addAll([
          if (widget.feeds.isEmpty)
            const Text('Add a feed product using the web inventory page before recording feeding.')
          else
            DropdownButtonFormField<int>(
              initialValue: _feedId,
              decoration: const InputDecoration(labelText: 'Feed product'),
              items: widget.feeds
                  .map((feed) => DropdownMenuItem<int>(
                        value: feed['id'] as int,
                        child: Text('${feed['name']} · ${_format(feed['stock_kg'])} kg'),
                      ))
                  .toList(),
              onChanged: (value) => setState(() => _feedId = value),
            ),
          _field('quantity_kg', 'Actual feed quantity (kg)', decimal: true),
          _field('fed_on', 'Feeding date (YYYY-MM-DD)', initial: today, keyboardType: TextInputType.datetime, numeric: false),
        ]);
        break;
    }
    fields.add(_field(
      'notes',
      'Notes (optional)',
      required: false,
      keyboardType: TextInputType.multiline,
      numeric: false,
    ));
    return AlertDialog(
      title: Text(title),
      content: SizedBox(
        width: 480,
        child: Form(
          key: _formKey,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                ...fields.map((field) => Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: field,
                    )),
                if (_error != null)
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                  ),
              ],
            ),
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(
          onPressed: () {
            final body = _buildBody();
            if (body != null) Navigator.pop(context, body);
          },
          child: const Text('Continue to video'),
        ),
      ],
    );
  }
}

class _MessageCard extends StatelessWidget {
  const _MessageCard({
    required this.message,
    this.isError = false,
    this.onDismiss,
  });

  final String message;
  final bool isError;
  final VoidCallback? onDismiss;

  @override
  Widget build(BuildContext context) {
    final color = isError ? Theme.of(context).colorScheme.error : const Color(0xff146c56);
    return Card(
      color: isError ? Theme.of(context).colorScheme.errorContainer : const Color(0xffe5f4ec),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Icon(isError ? Icons.error_outline : Icons.check_circle_outline, color: color),
            const SizedBox(width: 8),
            Expanded(child: Text(message)),
            if (onDismiss != null)
              IconButton(onPressed: onDismiss, icon: const Icon(Icons.close), visualDensity: VisualDensity.compact),
          ],
        ),
      ),
    );
  }
}

class _MetricCard extends StatelessWidget {
  const _MetricCard({required this.label, required this.value, required this.icon});

  final String label;
  final String value;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Icon(icon, color: const Color(0xff146c56)),
            Text(value, style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
            Text(label, style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}

class _ActionTile extends StatelessWidget {
  const _ActionTile({
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.onTap,
    this.busy = false,
    this.disabled = false,
  });

  final String title;
  final String subtitle;
  final IconData icon;
  final VoidCallback onTap;
  final bool busy;
  final bool disabled;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: Icon(icon, color: const Color(0xff146c56)),
        title: Text(title),
        subtitle: Text(subtitle),
        trailing: busy
            ? const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : const Icon(Icons.chevron_right),
        onTap: busy || disabled ? null : onTap,
      ),
    );
  }
}

class _InfoCard extends StatelessWidget {
  const _InfoCard({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: const Color(0xffedf5f0),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Text(text),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({
    required this.icon,
    required this.title,
    required this.message,
    this.action,
  });

  final IconData icon;
  final String title;
  final String message;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 48, color: const Color(0xff146c56)),
            const SizedBox(height: 12),
            Text(title, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 6),
            Text(message, textAlign: TextAlign.center),
            if (action != null) ...[
              const SizedBox(height: 16),
              action!,
            ],
          ],
        ),
      ),
    );
  }
}

String _format(Object? value) {
  if (value == null) return '0';
  final number = (value as num).toDouble();
  return number.toStringAsFixed(number.truncateToDouble() == number ? 0 : 2);
}

String _money(Object? value) {
  final amount = value == null ? '—' : _format(value);
  return 'GH₵ $amount';
}

void _snack(BuildContext context, String message, {bool isError = false}) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
    backgroundColor: isError ? Theme.of(context).colorScheme.error : null,
    content: Text(message),
  ));
}
