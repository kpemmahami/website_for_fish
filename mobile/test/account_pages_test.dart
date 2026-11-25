import 'dart:convert';

import 'package:aquafarm_mobile/account_pages.dart';
import 'package:aquafarm_mobile/api_client.dart';
import 'package:aquafarm_mobile/app_controller.dart';
import 'package:aquafarm_mobile/offline_store.dart';
import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets('farmer recovery requests an email link', (tester) async {
    final controller = AppController(OfflineStore());
    controller.api = ApiClient(
      baseUrl: 'https://farm.example',
      client: MockClient((request) async {
        expect(request.url.path, '/auth/password-recovery/request');
        expect(jsonDecode(request.body), {
          'email': 'farmer@example.com',
          'portal': 'farmer',
        });
        return http.Response(jsonEncode({'message': 'Check your email.'}), 202);
      }),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: PasswordRecoveryPage(
          controller: controller,
          email: 'farmer@example.com',
        ),
      ),
    );
    await tester.tap(find.text('Send reset link'));
    await tester.pumpAndSettle();
    expect(find.text('Check your email.'), findsOneWidget);
    controller.dispose();
  });

  testWidgets(
    'pending farmer can verify a saved phone without opening the workspace',
    (tester) async {
      final controller = AppController(OfflineStore());
      controller.user = {
        'account_type': 'pending_farmer',
        'phone_number': '+233245550001',
      };
      controller.api = ApiClient(
        baseUrl: 'https://farm.example',
        token: 'test-session',
        client: MockClient((request) async {
          expect(request.headers['authorization'], 'Bearer test-session');
          if (request.url.path.endsWith('/request')) {
            return http.Response.bytes(
              utf8.encode(jsonEncode({'destination': '•••0001', 'verified': false})),
              200,
              headers: {'Content-Type': 'application/json; charset=utf-8'},
            );
          }
          expect(request.url.path, '/auth/me/phone-verification/confirm');
          expect(jsonDecode(request.body), {'code': '548219'});
          return http.Response(
            jsonEncode({'phone_verified_at': '2026-11-25T00:00:00Z'}),
            200,
          );
        }),
      );
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: PhoneVerificationPanel(controller: controller)),
        ),
      );
      await tester.tap(find.text('Send SMS verification code'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), '548219');
      await tester.tap(find.text('Verify mobile number'));
      await tester.pumpAndSettle();
      expect(find.text('Mobile number verified.'), findsOneWidget);
      expect(controller.user?['account_type'], 'pending_farmer');
      controller.dispose();
    },
  );
}
