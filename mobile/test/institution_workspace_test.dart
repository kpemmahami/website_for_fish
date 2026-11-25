import 'dart:convert';

import 'package:aquafarm_mobile/api_client.dart';
import 'package:aquafarm_mobile/app_controller.dart';
import 'package:aquafarm_mobile/institution_workspace.dart';
import 'package:aquafarm_mobile/offline_store.dart';
import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets('verified collectors can open their institution collections', (
    tester,
  ) async {
    final controller = AppController(OfflineStore());
    controller.api = ApiClient(
      baseUrl: 'https://example.com',
      client: MockClient((request) async {
        if (request.url.path == '/finance/institutions/mine') {
          return http.Response(
            jsonEncode([
              {
                'id': 4,
                'name': 'Verified bank',
                'role': 'collections',
                'status': 'verified',
              },
              {
                'id': 5,
                'name': 'Suspended bank',
                'role': 'collections',
                'status': 'suspended',
              },
            ]),
            200,
          );
        }
        expect(request.url.path, '/finance/institutions/4/collections');
        return http.Response(
          jsonEncode({
            'items': [
              {
                'customer_name': 'Test borrower',
                'account_number': 'AQUA-LOAN-000001',
                'amount_ghs': 25,
              },
            ],
            'total_ghs': 25,
            'count': 1,
            'has_more': false,
          }),
          200,
        );
      }),
    );
    await tester.pumpWidget(
      MaterialApp(home: InstitutionWorkspace(controller: controller)),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Suspended bank'));
    await tester.pumpAndSettle();
    expect(find.text('Test borrower'), findsNothing);
    await tester.tap(find.text('Verified bank'));
    await tester.pumpAndSettle();
    expect(find.text('Test borrower'), findsOneWidget);
    expect(find.text('AQUA-LOAN-000001'), findsOneWidget);
    expect(find.text('GHS 25.00'), findsOneWidget);
    controller.dispose();
  });
}
