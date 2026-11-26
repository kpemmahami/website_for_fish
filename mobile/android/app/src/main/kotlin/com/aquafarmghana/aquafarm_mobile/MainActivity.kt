package com.aquafarmghana.aquafarm_mobile

import android.app.Dialog
import android.content.pm.ApplicationInfo
import android.net.Uri
import android.view.ViewGroup
import android.widget.MediaController
import android.widget.VideoView
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "aquafarm/collection-video")
            .setMethodCallHandler { call, result ->
                if (call.method != "play") {
                    result.notImplemented()
                    return@setMethodCallHandler
                }
                val url = call.argument<String>("url")
                val token = call.argument<String>("token")
                val uri = url?.let(Uri::parse)
                val debugBuild = (applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE) != 0
                val localEmulator = debugBuild && uri?.scheme == "http" && uri.host == "10.0.2.2"
                if (uri == null || (uri.scheme != "https" && !localEmulator) || token.isNullOrBlank()) {
                    result.error("VIDEO_ACCESS", "An authenticated HTTPS session is required.", null)
                    return@setMethodCallHandler
                }

                val dialog = Dialog(this)
                val video = VideoView(this)
                val controls = MediaController(this)
                video.setMediaController(controls)
                controls.setAnchorView(video)
                dialog.setContentView(video)
                dialog.setOnDismissListener { video.stopPlayback() }
                video.setOnPreparedListener { video.start() }
                video.setVideoURI(uri, mapOf("Authorization" to "Bearer $token"))
                dialog.show()
                dialog.window?.setLayout(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                )
                result.success(null)
            }
    }
}
