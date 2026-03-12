/**
 * process_raw.jsx
 * Adobe Photoshop ExtendScript - RAW to JPEG processor using Camera Raw engine
 *
 * NOTE: SUPERSEDED — use tools/raw_to_jpeg.py instead.
 * This script required Photoshop 2026 + Camera Raw 18, which always shows its
 * dialog regardless of DialogModes.NO / CameraRAWOpenOptions, blocking headless use.
 * raw_to_jpeg.py uses rawpy (LibRaw) and is fully headless with no Adobe dependency.
 *
 * Usage: Called by raw_to_jpeg.py via Photoshop.exe
 * Arguments passed via a JSON settings file: .tmp/raw_processing_job.json
 *
 * Settings JSON schema:
 * {
 *   "inputFolder":  "C:/path/to/raw/images",
 *   "outputFolder": "C:/path/to/.tmp/Processed",
 *   "jpegQuality":  10,          // 1-12 (default: 10)
 *   "colorSpace":   "sRGB",      // "sRGB" | "AdobeRGB" | "ProPhotoRGB" (default: sRGB)
 *   "resolution":   300,         // DPI (default: 300)
 *   "size":         "large",     // "large" | "medium" | "small" | "extralarge" (default: large)
 *   "whiteBalance": "asShot",    // "asShot" | "auto" | "daylight" | "cloudy" | "shade" |
 *                                //  "tungsten" | "fluorescent" | "flash" | "custom"
 *   "temperature":  null,        // 2000-50000 K (only used if whiteBalance = "custom")
 *   "tint":         null,        // -150 to 150 (only used if whiteBalance = "custom")
 *   "exposure":     0.0,         // -4.0 to 4.0
 *   "contrast":     0,           // -50 to 100
 *   "highlights":   0,           // -100 to 100
 *   "shadows":      5,           // 0 to 100
 *   "whites":       0,           // -100 to 100
 *   "blacks":       0,           // 0 to 100
 *   "clarity":      0,           // -100 to 100
 *   "saturation":   0,           // -100 to 100
 *   "vibrance":     0,           // -100 to 100
 *   "sharpness":    25,          // 0 to 100
 *   "luminanceSmoothing": 0,     // 0 to 100
 *   "colorNoiseReduction": 25    // 0 to 100
 * }
 */

#target photoshop

// ─── Helpers ────────────────────────────────────────────────────────────────

function readFile(path) {
    var f = new File(path);
    if (!f.exists) { throw new Error("Settings file not found: " + path); }
    f.open("r");
    var content = f.read();
    f.close();
    return content;
}

function parseJSON(str) {
    // Basic JSON parser via eval (safe here; we control the input file)
    return eval("(" + str + ")");
}

function getSettingsPath() {
    // Settings file is always .tmp/raw_processing_job.json relative to script location
    // or passed via command-line argument (Bridge/Photoshop arg passing is limited)
    // We resolve relative to the script's parent-parent directory
    var scriptFile = new File($.fileName);
    var projectRoot = scriptFile.parent.parent;  // tools/../ = project root
    return projectRoot.fsName + "/.tmp/raw_processing_job.json";
}

function log(message) {
    var logFile = new File(getSettingsPath().replace("raw_processing_job.json", "raw_processing.log"));
    logFile.open("a");
    logFile.writeln("[" + new Date().toISOString() + "] " + message);
    logFile.close();
}

// ─── Camera Raw Size Mapping ─────────────────────────────────────────────────

function getCameraRAWSize(sizeStr) {
    var map = {
        "small":      CameraRAWSize.MINIMUM,
        "medium":     CameraRAWSize.MEDIUM,
        "large":      CameraRAWSize.LARGE,
        "extralarge": CameraRAWSize.EXTRALARGE,
        "maximum":    CameraRAWSize.MAXIMUM
    };
    return map[(sizeStr || "large").toLowerCase()] || CameraRAWSize.LARGE;
}

// ─── White Balance Mapping ────────────────────────────────────────────────────

function getWhiteBalance(wbStr) {
    var map = {
        "asshot":      WhiteBalanceType.ASSHOT,
        "as shot":     WhiteBalanceType.ASSHOT,
        "auto":        WhiteBalanceType.AUTO,
        "daylight":    WhiteBalanceType.DAYLIGHT,
        "cloudy":      WhiteBalanceType.CLOUDY,
        "shade":       WhiteBalanceType.SHADE,
        "tungsten":    WhiteBalanceType.TUNGSTEN,
        "fluorescent": WhiteBalanceType.FLUORESCENT,
        "flash":       WhiteBalanceType.FLASH,
        "custom":      WhiteBalanceType.CUSTOM
    };
    return map[(wbStr || "asshot").toLowerCase()] || WhiteBalanceType.ASSHOT;
}

// ─── Color Space Mapping ──────────────────────────────────────────────────────

function getColorSpace(csStr) {
    var map = {
        "srgb":         ColorSpace.SRGB,
        "adobergb":     ColorSpace.ADOBERGB,
        "prophoto":     ColorSpace.PROPHOTOORGB,
        "prophotoorgb": ColorSpace.PROPHOTOORGB,
        "colormatch":   ColorSpace.COLORMATCH
    };
    return map[(csStr || "srgb").toLowerCase().replace(/[^a-z]/g, "")] || ColorSpace.SRGB;
}

// ─── RAW File Filter ──────────────────────────────────────────────────────────

var RAW_EXTENSIONS = /\.(cr2|cr3|nef|nrw|arw|srf|sr2|raf|dng|orf|rw2|pef|srw|3fr|mef|mrw|rwl|x3f|erf)$/i;

// ─── Main Processing ──────────────────────────────────────────────────────────

function main() {
    var settingsPath = getSettingsPath();
    log("Reading settings from: " + settingsPath);

    var settings = parseJSON(readFile(settingsPath));

    var inputFolder  = new Folder(settings.inputFolder);
    var outputFolder = new Folder(settings.outputFolder);

    if (!inputFolder.exists) {
        throw new Error("Input folder does not exist: " + settings.inputFolder);
    }
    if (!outputFolder.exists) {
        outputFolder.create();
        log("Created output folder: " + settings.outputFolder);
    }

    // Suppress all dialogs
    app.displayDialogs = DialogModes.NO;

    // Gather RAW files
    var allFiles = inputFolder.getFiles();
    var rawFiles = [];
    for (var i = 0; i < allFiles.length; i++) {
        if (allFiles[i] instanceof File && RAW_EXTENSIONS.test(allFiles[i].name)) {
            rawFiles.push(allFiles[i]);
        }
    }

    log("Found " + rawFiles.length + " RAW file(s) to process");

    if (rawFiles.length === 0) {
        throw new Error("No RAW files found in: " + settings.inputFolder);
    }

    var processed = [];
    var failed    = [];

    for (var j = 0; j < rawFiles.length; j++) {
        var rawFile = rawFiles[j];
        log("Processing (" + (j + 1) + "/" + rawFiles.length + "): " + rawFile.name);

        try {
            // ── Build CameraRAWOpenOptions ────────────────────────────────
            var opts = new CameraRAWOpenOptions();

            // Colour
            opts.colorSpace       = getColorSpace(settings.colorSpace);
            opts.bitsPerChannel   = BitsPerChannelType.EIGHT;
            opts.resolution       = settings.resolution  || 300;
            opts.size             = getCameraRAWSize(settings.size);

            // White Balance
            opts.whiteBalance = getWhiteBalance(settings.whiteBalance);
            if (opts.whiteBalance === WhiteBalanceType.CUSTOM) {
                if (settings.temperature != null) opts.temperature = settings.temperature;
                if (settings.tint        != null) opts.tint        = settings.tint;
            }

            // Tone
            if (settings.exposure  != null) opts.exposure  = settings.exposure;
            if (settings.contrast  != null) opts.contrast  = settings.contrast;
            if (settings.highlights!= null) opts.highlights= settings.highlights;
            if (settings.shadows   != null) opts.shadows   = settings.shadows;
            if (settings.whites    != null) opts.whites    = settings.whites;
            if (settings.blacks    != null) opts.blacks    = settings.blacks;

            // Presence
            if (settings.saturation != null) opts.saturation = settings.saturation;
            if (settings.vibrance   != null) opts.vibrance   = settings.vibrance;
            if (settings.clarity    != null) opts.clarity    = settings.clarity;

            // Detail
            if (settings.sharpness          != null) opts.sharpness          = settings.sharpness;
            if (settings.luminanceSmoothing != null) opts.luminanceSmoothing = settings.luminanceSmoothing;
            if (settings.colorNoiseReduction!= null) opts.colorNoiseReduction= settings.colorNoiseReduction;

            // ── Open RAW via Camera Raw (no dialog) ───────────────────────
            var doc = app.open(rawFile, opts);

            // ── Build output JPEG path ─────────────────────────────────────
            var baseName  = rawFile.name.replace(/\.[^.]+$/, "");
            var jpegPath  = settings.outputFolder + "/" + baseName + ".jpg";
            var jpegFile  = new File(jpegPath);

            // ── Save as JPEG ───────────────────────────────────────────────
            var saveOpts         = new JPEGSaveOptions();
            saveOpts.quality     = settings.jpegQuality || 10;  // 1-12
            saveOpts.embedColorProfile = true;
            saveOpts.formatOptions     = FormatOptions.STANDARDBASELINE;
            saveOpts.matte             = MatteType.NONE;

            doc.saveAs(jpegFile, saveOpts, true, Extension.LOWERCASE);
            doc.close(SaveOptions.DONOTSAVECHANGES);

            log("Saved: " + jpegPath);
            processed.push(jpegPath);

        } catch (e) {
            log("ERROR processing " + rawFile.name + ": " + e.message);
            failed.push({ file: rawFile.name, error: e.message });
        }
    }

    // ── Write results JSON ────────────────────────────────────────────────────
    var resultsPath = getSettingsPath().replace("raw_processing_job.json", "raw_processing_results.json");
    var resultsFile = new File(resultsPath);
    resultsFile.open("w");
    resultsFile.write(
        '{"processed":' + JSON.stringify(processed) +
        ',"failed":'    + JSON.stringify(failed)     +
        ',"total":'     + rawFiles.length            + '}'
    );
    resultsFile.close();

    log("Done. Processed: " + processed.length + " | Failed: " + failed.length);
}

// JSON.stringify polyfill for ExtendScript
if (typeof JSON === "undefined") {
    JSON = {};
    JSON.stringify = function(obj) {
        if (obj === null)              return "null";
        if (typeof obj === "boolean")  return String(obj);
        if (typeof obj === "number")   return isFinite(obj) ? String(obj) : "null";
        if (typeof obj === "string")   return '"' + obj.replace(/\\/g,"\\\\").replace(/"/g,'\\"').replace(/\n/g,"\\n").replace(/\r/g,"\\r") + '"';
        if (obj instanceof Array) {
            var a = [];
            for (var i = 0; i < obj.length; i++) a.push(JSON.stringify(obj[i]));
            return "[" + a.join(",") + "]";
        }
        if (typeof obj === "object") {
            var p = [];
            for (var k in obj) {
                if (obj.hasOwnProperty(k)) p.push('"' + k + '":' + JSON.stringify(obj[k]));
            }
            return "{" + p.join(",") + "}";
        }
        return "null";
    };
}

main();
