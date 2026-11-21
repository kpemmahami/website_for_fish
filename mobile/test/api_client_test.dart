import 'dart:convert';

import 'package:aquafarm_mobile/api_client.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('sends authenticated requests to the configured backend', () async {
    final client = MockClient((request) async {
      expect(request.url.toString(), 'https://farm.example/api/auth/me');
      expect(request.headers['authorization'], 'Bearer session-token');
      return http.Response(jsonEncode({'id': 7}), 200);
    });
    final api = ApiClient(
      baseUrl: 'https://farm.example/api',
      token: 'session-token',
      client: client,
    );

    expect(await api.get('/auth/me'), {'id': 7});
    api.close();
  });

  test('surfaces backend validation errors', () async {
    final api = ApiClient(
      baseUrl: 'https://farm.example',
      client: MockClient((_) async => http.Response(
            jsonEncode({'detail': 'Select an active stocking cycle'}),
            422,
          )),
    );

    await expectLater(
      api.get('/farms/1/units'),
      throwsA(
        isA<ApiException>().having(
          (error) => error.message,
          'message',
          'Select an active stocking cycle',
        ),
      ),
    );
    api.close();
  });
}
