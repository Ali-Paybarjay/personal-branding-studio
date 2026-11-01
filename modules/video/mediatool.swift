// ابزار تصویر تدوین ویدیو (فاز ۳) — فقط چارچوب‌های خود macOS (ImageIO، CoreGraphics، Vision، CoreImage)؛ بدون نصب.
// ساخت: swiftc -O -parse-as-library mediatool.swift -o bin/mediatool   (video_visuals.ensure_mediatool خودکار می‌سازد)
// همه‌ی جعبه‌ها کسری از عرض و ارتفاع‌اند، مبدأ بالا-چپ: [x, y, w, h]. خروجی هر فرمان یک JSON روی stdout.
//   norm   <in> <out> <maxpx>         عکس (HEIC/JPEG/PNG/WebP/TIFF/GIF) با چرخش EXIF اعمال‌شده، حداکثر maxpx؛ PNG اگر شفافیت دارد
//   pdf    <in.pdf> <out.png> <maxpx> صفحه‌ی اول PDF روی زمینه‌ی سفید
//   ocr    <img>                      خط‌های متن با جعبه‌ی هر خط و هر کلمه (Vision، دقیق)
//   faces  <img>                      جعبه‌ی صورت‌ها
//   cutout <img> <out.png>            سوژه بدون پس‌زمینه (Vision foreground mask، macOS 14+)، بریده تا لبه‌ی سوژه
//   faceq  <img>…                     برای کاور (فاز ۶): هر عکس یک خط JSON؛ هر صورت: b جعبه، q کیفیت عکس صورت (Vision، ۰ تا ۱)،
//                                     eye بازبودن چشم بسته‌تر (ارتفاع/پهنای دور چشم)، mouth بازبودن دهان (لب داخلی)، yaw چرخش سر (رادیان)
import Foundation
import ImageIO
import CoreGraphics
import CoreImage
import Vision
import UniformTypeIdentifiers

func out(_ o: Any) {
    let d = try! JSONSerialization.data(withJSONObject: o, options: [])
    FileHandle.standardOutput.write(d)
    FileHandle.standardOutput.write("\n".data(using: .utf8)!)
}

func fail(_ m: String) -> Never {
    FileHandle.standardError.write((m + "\n").data(using: .utf8)!)
    exit(1)
}

func r3(_ v: CGFloat) -> Double { (Double(v) * 10000).rounded() / 10000 }

// Vision: مبدأ پایین-چپ → بالا-چپ
func box(_ b: CGRect) -> [Double] { [r3(b.minX), r3(1 - b.maxY), r3(b.width), r3(b.height)] }

func loadImage(_ path: String, maxpx: Int? = nil) -> CGImage {
    guard let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil) else { fail("cannot open image") }
    var opts: [CFString: Any] = [kCGImageSourceCreateThumbnailFromImageAlways: true,
                                 kCGImageSourceCreateThumbnailWithTransform: true,
                                 kCGImageSourceShouldCacheImmediately: true]
    if let m = maxpx {
        opts[kCGImageSourceThumbnailMaxPixelSize] = m
    } else if let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any],
              let w = props[kCGImagePropertyPixelWidth] as? Int, let h = props[kCGImagePropertyPixelHeight] as? Int {
        opts[kCGImageSourceThumbnailMaxPixelSize] = max(w, h)
    }
    guard let img = CGImageSourceCreateThumbnailAtIndex(src, 0, opts as CFDictionary) else { fail("cannot decode image") }
    return img
}

func hasAlpha(_ img: CGImage) -> Bool {
    switch img.alphaInfo {
    case .none, .noneSkipFirst, .noneSkipLast: return false
    default: break
    }
    // کانال آلفا هست؛ آیا واقعاً پیکسل شفاف دارد؟ (نمونه‌برداری درشت)
    let w = 64, h = 64
    guard let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4,
                              space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return true }
    ctx.draw(img, in: CGRect(x: 0, y: 0, width: w, height: h))
    guard let p = ctx.data?.assumingMemoryBound(to: UInt8.self) else { return true }
    for i in 0..<(w * h) where p[i * 4 + 3] < 250 { return true }
    return false
}

func write(_ img: CGImage, _ path: String, png: Bool) {
    let url = URL(fileURLWithPath: path) as CFURL
    let type = (png ? UTType.png : UTType.jpeg).identifier as CFString
    guard let dst = CGImageDestinationCreateWithURL(url, type, 1, nil) else { fail("cannot write") }
    let props: [CFString: Any] = png ? [:] : [kCGImageDestinationLossyCompressionQuality: 0.9]
    CGImageDestinationAddImage(dst, img, props as CFDictionary)
    if !CGImageDestinationFinalize(dst) { fail("write failed") }
}

func flatten(_ img: CGImage) -> CGImage {
    // JPEG شفافیت ندارد: روی سفید
    let w = img.width, h = img.height
    let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                        space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
    ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.draw(img, in: CGRect(x: 0, y: 0, width: w, height: h))
    return ctx.makeImage()!
}

func cmdNorm(_ a: [String]) {
    guard a.count >= 3, let m = Int(a[2]) else { fail("usage: norm <in> <out> <maxpx>") }
    let img = loadImage(a[0], maxpx: m)
    let alpha = hasAlpha(img)
    let png = a[1].lowercased().hasSuffix(".png")      // پسوند خروجی تعیین می‌کند؛ JPEG روی زمینه‌ی سفید
    write(png ? img : flatten(img), a[1], png: png)
    out(["w": img.width, "h": img.height, "alpha": alpha])
}

func cmdPdf(_ a: [String]) {
    guard a.count >= 3, let m = Int(a[2]) else { fail("usage: pdf <in> <out.png> <maxpx>") }
    guard let doc = CGPDFDocument(URL(fileURLWithPath: a[0]) as CFURL), let page = doc.page(at: 1) else { fail("cannot open pdf") }
    let mb = page.getBoxRect(.cropBox)
    let rot = page.rotationAngle % 180 != 0
    let pw = rot ? mb.height : mb.width, ph = rot ? mb.width : mb.height
    let s = CGFloat(m) / max(pw, ph)
    let w = Int((pw * s).rounded()), h = Int((ph * s).rounded())
    let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                        space: CGColorSpace(name: CGColorSpace.sRGB)!, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
    ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.interpolationQuality = .high
    // getDrawingTransform هرگز بزرگ نمی‌کند (صفحه ۱:۱ وسط بوم می‌ماند)؛ پس تبدیل دستی، با چرخش صفحه
    let ang = ((Int(page.rotationAngle) % 360) + 360) % 360
    switch ang {
    case 90: ctx.translateBy(x: 0, y: CGFloat(h)); ctx.rotate(by: -.pi / 2)
    case 180: ctx.translateBy(x: CGFloat(w), y: CGFloat(h)); ctx.rotate(by: .pi)
    case 270: ctx.translateBy(x: CGFloat(w), y: 0); ctx.rotate(by: .pi / 2)
    default: break
    }
    ctx.scaleBy(x: s, y: s)
    ctx.translateBy(x: -mb.minX, y: -mb.minY)
    ctx.drawPDFPage(page)
    write(ctx.makeImage()!, a[1], png: true)
    out(["w": w, "h": h, "pages": doc.numberOfPages])
}

func cmdOcr(_ a: [String]) {
    guard a.count >= 1 else { fail("usage: ocr <img>") }
    let img = loadImage(a[0])
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = true
    req.automaticallyDetectsLanguage = true
    do { try VNImageRequestHandler(cgImage: img, options: [:]).perform([req]) } catch { fail("ocr: \(error)") }
    var lines: [[String: Any]] = []
    for o in req.results ?? [] {
        guard let c = o.topCandidates(1).first else { continue }
        let s = c.string
        var words: [[String: Any]] = []
        s.enumerateSubstrings(in: s.startIndex..<s.endIndex, options: .byWords) { sub, r, _, _ in
            guard let sub = sub, let b = try? c.boundingBox(for: r)?.boundingBox else { return }
            words.append(["t": sub, "b": box(b)])
        }
        lines.append(["t": s, "c": r3(CGFloat(c.confidence)), "b": box(o.boundingBox), "w": words])
    }
    lines.sort { (($0["b"] as! [Double])[1], ($0["b"] as! [Double])[0]) < (($1["b"] as! [Double])[1], ($1["b"] as! [Double])[0]) }
    out(["w": img.width, "h": img.height, "lines": lines])
}

func cmdFaces(_ a: [String]) {
    guard a.count >= 1 else { fail("usage: faces <img>") }
    let img = loadImage(a[0], maxpx: 1600)
    let req = VNDetectFaceRectanglesRequest()
    do { try VNImageRequestHandler(cgImage: img, options: [:]).perform([req]) } catch { fail("faces: \(error)") }
    out(["faces": (req.results ?? []).filter { $0.confidence >= 0.5 }.map { box($0.boundingBox) }])
}

func iou(_ a: CGRect, _ b: CGRect) -> CGFloat {
    let i = a.intersection(b)
    if i.isNull { return 0 }
    let u = a.width * a.height + b.width * b.height - i.width * i.height
    return u > 0 ? i.width * i.height / u : 0
}

// ارتفاع به پهنای نقطه‌های یک ناحیه‌ی چهره (چشم یا لب)؛ ۰ یعنی پیدا نشد
func openness(_ r: VNFaceLandmarkRegion2D?) -> CGFloat {
    guard let pts = r?.normalizedPoints, pts.count >= 3 else { return 0 }
    let xs = pts.map { $0.x }, ys = pts.map { $0.y }
    let w = (xs.max() ?? 0) - (xs.min() ?? 0)
    return w > 0 ? ((ys.max() ?? 0) - (ys.min() ?? 0)) / w : 0
}

func cmdFaceq(_ a: [String]) {
    guard !a.isEmpty else { fail("usage: faceq <img>…") }
    for path in a {
        guard FileManager.default.fileExists(atPath: path) else { out(["f": path, "faces": [Any]()]); continue }
        let img = loadImage(path, maxpx: 1280)
        let q = VNDetectFaceCaptureQualityRequest()
        let lm = VNDetectFaceLandmarksRequest()
        do { try VNImageRequestHandler(cgImage: img, options: [:]).perform([q, lm]) } catch {
            out(["f": path, "faces": [Any]()]); continue
        }
        let marks = lm.results ?? []
        var faces: [[String: Any]] = []
        for o in q.results ?? [] {
            var f: [String: Any] = ["b": box(o.boundingBox), "q": r3(CGFloat(o.faceCaptureQuality ?? 0))]
            if let y = o.yaw { f["yaw"] = r3(CGFloat(truncating: y)) }
            if let m = marks.max(by: { iou($0.boundingBox, o.boundingBox) < iou($1.boundingBox, o.boundingBox) }),
               iou(m.boundingBox, o.boundingBox) > 0.3, let l = m.landmarks {
                let le = openness(l.leftEye), re = openness(l.rightEye)
                f["eye"] = r3(le > 0 && re > 0 ? min(le, re) : max(le, re))
                f["mouth"] = r3(openness(l.innerLips))
            }
            faces.append(f)
        }
        out(["f": path, "w": img.width, "h": img.height, "faces": faces])
    }
}

func cmdCutout(_ a: [String]) {
    guard a.count >= 2 else { fail("usage: cutout <img> <out.png>") }
    guard #available(macOS 14.0, *) else { fail("cutout needs macOS 14") }
    let img = loadImage(a[0], maxpx: 2000)
    let handler = VNImageRequestHandler(cgImage: img, options: [:])
    let req = VNGenerateForegroundInstanceMaskRequest()
    do { try handler.perform([req]) } catch { fail("cutout: \(error)") }
    guard let r = req.results?.first, !r.allInstances.isEmpty else { out(["ok": false]); return }
    guard let buf = try? r.generateMaskedImage(ofInstances: r.allInstances, from: handler, croppedToInstancesExtent: true) else {
        out(["ok": false]); return
    }
    let ci = CIImage(cvPixelBuffer: buf)
    guard let cg = CIContext().createCGImage(ci, from: ci.extent) else { out(["ok": false]); return }
    write(cg, a[1], png: true)
    out(["ok": true, "w": cg.width, "h": cg.height])
}

@main
struct Main {
    static func main() {
        let args = Array(CommandLine.arguments.dropFirst())
        guard let cmd = args.first else { fail("usage: mediatool norm|pdf|ocr|faces|cutout|faceq …") }
        let rest = Array(args.dropFirst())
        switch cmd {
        case "norm": cmdNorm(rest)
        case "pdf": cmdPdf(rest)
        case "ocr": cmdOcr(rest)
        case "faces": cmdFaces(rest)
        case "cutout": cmdCutout(rest)
        case "faceq": cmdFaceq(rest)
        default: fail("unknown command \(cmd)")
        }
    }
}
