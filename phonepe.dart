import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

void main() {
  runApp(const ScannerApp());
}

class ScannerApp extends StatelessWidget {
  const ScannerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Scanner Pro',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: Colors.black,
        appBarTheme: const AppBarTheme(
          backgroundColor: Colors.transparent,
          elevation: 0,
          iconTheme: IconThemeData(color: Colors.white),
          titleTextStyle: TextStyle(
            color: Colors.white,
            fontSize: 20,
            fontWeight: FontWeight.w600,
          ),
        ),
        useMaterial3: true,
      ),
      home: const ScannerScreen(),
    );
  }
}

class ScannerScreen extends StatefulWidget {
  const ScannerScreen({super.key});

  @override
  State<ScannerScreen> createState() => _ScannerScreenState();
}

class _ScannerScreenState extends State<ScannerScreen>
    with SingleTickerProviderStateMixin {
  // ============================================================
  // 🔽 CONFIGURATION ZONE - TWEAK SCANNER VALUES HERE 🔽
  // ============================================================

  // 1. BOX DIMENSIONS & BREATHING
  // How wide the scanner is relative to screen width (0.85 = 85%)
  final double scanAreaWidthFactor = 0.80;

  // How many pixels the box shrinks when the lines expand.
  // REDUCE this value (e.g., 10.0) for less shrinking.
  // Set to 0.0 to disable shrinking entirely.
  final double breathingShrink = 15.0;

  // 2. CORNER LINES ANIMATION
  // The purple lines get longer/shorter. Adjust these limits.
  final double minLineLength = 8.0; // Shortest length
  final double maxLineLength = 28.0; // Longest length

  // 3. STYLE & COLORS
  final double cornerInset =
      25.0; // Gap between the clear cutout and the purple lines
  final double borderRadius = 24.0; // Roundness of the corners
  final double strokeWidth = 3.5; // Thickness of the purple lines
  final Color scannerColor = const Color(0xFF9747FF); // The purple color

  // 4. ANIMATION SPEED
  // NOTE: If you change this, you must press the FULL RESTART button (Green Arrow)
  final Duration animDuration = const Duration(milliseconds: 1000);

  // ============================================================
  // 🔼 END OF CONFIGURATION 🔼
  // ============================================================

  late MobileScannerController controller;
  bool isFlashOn = false;

  late AnimationController _animationController;
  late Animation<double> _animValue;

  @override
  void initState() {
    super.initState();
    controller = MobileScannerController(
      detectionSpeed: DetectionSpeed.noDuplicates,
      returnImage: true,
    );

    // Main animation loop
    _animationController = AnimationController(
      duration: animDuration,
      vsync: this,
    )..repeat(reverse: true);

    // A simple 0.0 to 1.0 curve
    _animValue = CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeInOut,
    );
  }

  @override
  void dispose() {
    controller.dispose();
    _animationController.dispose();
    super.dispose();
  }

  void _toggleFlash() {
    setState(() {
      isFlashOn = !isFlashOn;
      controller.toggleTorch();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new, size: 22),
          onPressed: () {
            // Navigator.pop(context);
          },
        ),
        title: const Text("Scan QR Code"),
        centerTitle: true,
        actions: [
          IconButton(
            icon: Icon(
              isFlashOn ? Icons.flash_on : Icons.flash_off,
              color: isFlashOn ? Colors.yellow : Colors.white,
            ),
            onPressed: _toggleFlash,
          ),
          const SizedBox(width: 8),
        ],
      ),
      backgroundColor: Colors.black,
      body: AnimatedBuilder(
        animation: _animValue,
        builder: (context, child) {
          // --- CALCULATE ANIMATED VALUES ---
          // t goes from 0.0 to 1.0
          final double t = _animValue.value;

          // 1. Calculate Scan Window Size (Inverse relationship)
          // When t=0 (lines short), size is max (base).
          // When t=1 (lines long), size is min (base - shrink).
          final double screenWidth = MediaQuery.of(context).size.width;
          final double initialSize =
              screenWidth * scanAreaWidthFactor; // Updated variable name
          final double currentSize =
              initialSize - (t * breathingShrink); // Updated variable name

          // Center the box
          final double scanTop =
              (MediaQuery.of(context).size.height - currentSize) / 2 - 40;
          final double scanLeft = (screenWidth - currentSize) / 2;

          final Rect scanWindow = Rect.fromLTWH(
            scanLeft,
            scanTop,
            currentSize,
            currentSize,
          );

          // 2. Calculate Corner Line Length (Direct relationship)
          // When t=0, length is min. When t=1, length is max.
          final double currentCornerLength =
              minLineLength +
              (t * (maxLineLength - minLineLength)); // Updated variable names

          return Stack(
            children: [
              // 1. Camera Layer
              // Note: We pass the animated scanWindow here so detection focuses on the shrinking box
              MobileScanner(
                controller: controller,
                scanWindow: scanWindow,
                onDetect: (capture) {
                  final List<Barcode> barcodes = capture.barcodes;
                  for (final barcode in barcodes) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text('Detected: ${barcode.rawValue}'),
                        backgroundColor: scannerColor,
                        duration: const Duration(
                          milliseconds: 500,
                        ), // Short duration to avoid stacking
                      ),
                    );
                  }
                },
              ),

              // 2. Animated Overlay
              CustomPaint(
                painter: ScannerOverlayPainter(
                  scanWindow: scanWindow,
                  borderRadius: borderRadius,
                  cornerExtension: currentCornerLength,
                  color: scannerColor,
                  strokeWidth: strokeWidth,
                  inset: cornerInset,
                ),
                child: Container(),
              ),

              // 3. Helper Text (Anchored to bottom of dynamic box)
              Positioned(
                top: scanWindow.bottom + 40,
                left: 0,
                right: 0,
                child: const Column(
                  children: [
                    Text(
                      "Align code within the frame to scan",
                      style: TextStyle(
                        color: Colors.white70,
                        fontSize: 14,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ],
                ),
              ),

              // 4. Bottom Controls (Static position)
              Positioned(
                bottom: 60,
                left: 0,
                right: 0,
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    _buildBottomAction(Icons.image_outlined, "Gallery"),

                    GestureDetector(
                      onTap: () {},
                      child: Container(
                        width: 72,
                        height: 72,
                        decoration: BoxDecoration(
                          color: Colors.white,
                          shape: BoxShape.circle,
                          boxShadow: [
                            BoxShadow(
                              color: scannerColor.withOpacity(0.5),
                              blurRadius: 20,
                              spreadRadius: 2,
                            ),
                          ],
                        ),
                        child: const Center(
                          child: Icon(
                            Icons.qr_code_scanner,
                            color: Colors.black,
                            size: 32,
                          ),
                        ),
                      ),
                    ),

                    _buildBottomAction(Icons.history, "History"),
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildBottomAction(IconData icon, String label) {
    return GestureDetector(
      onTap: () {},
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.1),
              shape: BoxShape.circle,
            ),
            child: Icon(icon, color: Colors.white, size: 24),
          ),
          const SizedBox(height: 8),
          Text(
            label,
            style: const TextStyle(color: Colors.white60, fontSize: 12),
          ),
        ],
      ),
    );
  }
}

// --- Custom Painter ---
class ScannerOverlayPainter extends CustomPainter {
  final Rect scanWindow;
  final double borderRadius;
  final double cornerExtension;
  final Color color;
  final double strokeWidth;
  final double inset;

  ScannerOverlayPainter({
    required this.scanWindow,
    required this.borderRadius,
    required this.cornerExtension,
    required this.color,
    required this.strokeWidth,
    required this.inset,
  });

  @override
  void paint(Canvas canvas, Size size) {
    // 1. Darken Background
    final backgroundPath = Path()
      ..addRect(Rect.fromLTWH(0, 0, size.width, size.height));

    // Create the cutout rect (rounded)
    final cutoutRRect = RRect.fromRectAndRadius(
      scanWindow,
      Radius.circular(borderRadius),
    );

    final cutoutPath = Path()..addRRect(cutoutRRect);

    final backgroundPaint = Paint()
      ..color = Colors.black.withOpacity(0.6)
      ..style = PaintingStyle.fill;

    // Subtract cutout from background
    final overlayPath = Path.combine(
      PathOperation.difference,
      backgroundPath,
      cutoutPath,
    );

    canvas.drawPath(overlayPath, backgroundPaint);

    // 2. Draw Rounded Corners INSIDE the scan area
    // We deflect (inset) the rect so the corners are inside the clear window
    final Rect innerRect = scanWindow.deflate(inset);

    // Calculate a concentric inner radius (Outer Radius - Inset)
    // ensuring it doesn't go below a reasonable minimum
    final double innerRadius = (borderRadius - inset).clamp(10.0, borderRadius);

    final borderPaint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round;

    // Helper to draw a corner

    // Top Left Corner
    final tlPath = Path();
    tlPath.moveTo(
      innerRect.left,
      innerRect.top + innerRadius + cornerExtension,
    );
    tlPath.lineTo(innerRect.left, innerRect.top + innerRadius);
    tlPath.arcToPoint(
      Offset(innerRect.left + innerRadius, innerRect.top),
      radius: Radius.circular(innerRadius),
      clockwise: true,
    );
    tlPath.lineTo(
      innerRect.left + innerRadius + cornerExtension,
      innerRect.top,
    );
    canvas.drawPath(tlPath, borderPaint);

    // Top Right Corner
    final trPath = Path();
    trPath.moveTo(
      innerRect.right - innerRadius - cornerExtension,
      innerRect.top,
    );
    trPath.lineTo(innerRect.right - innerRadius, innerRect.top);
    trPath.arcToPoint(
      Offset(innerRect.right, innerRect.top + innerRadius),
      radius: Radius.circular(innerRadius),
      clockwise: true,
    );
    trPath.lineTo(
      innerRect.right,
      innerRect.top + innerRadius + cornerExtension,
    );
    canvas.drawPath(trPath, borderPaint);

    // Bottom Right Corner
    final brPath = Path();
    brPath.moveTo(
      innerRect.right,
      innerRect.bottom - innerRadius - cornerExtension,
    );
    brPath.lineTo(innerRect.right, innerRect.bottom - innerRadius);
    brPath.arcToPoint(
      Offset(innerRect.right - innerRadius, innerRect.bottom),
      radius: Radius.circular(innerRadius),
      clockwise: true,
    );
    brPath.lineTo(
      innerRect.right - innerRadius - cornerExtension,
      innerRect.bottom,
    );
    canvas.drawPath(brPath, borderPaint);

    // Bottom Left Corner
    final blPath = Path();
    blPath.moveTo(
      innerRect.left + innerRadius + cornerExtension,
      innerRect.bottom,
    );
    blPath.lineTo(innerRect.left + innerRadius, innerRect.bottom);
    blPath.arcToPoint(
      Offset(innerRect.left, innerRect.bottom - innerRadius),
      radius: Radius.circular(innerRadius),
      clockwise: true,
    );
    // FIXED: Removed the extra third argument
    blPath.lineTo(
      innerRect.left,
      innerRect.bottom - innerRadius - cornerExtension,
    );
    canvas.drawPath(blPath, borderPaint);
  }

  @override
  bool shouldRepaint(ScannerOverlayPainter oldDelegate) {
    return oldDelegate.cornerExtension != cornerExtension ||
        oldDelegate.scanWindow != scanWindow;
  }
}
