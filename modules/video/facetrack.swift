// جای صورت در طول ویدیو، با Vision خود macOS (محلی، رایگان، روی Neural Engine).
// استفاده: facetrack <video> [fps=4]
// خروجی: هر نمونه یک خط JSON  {"t":1.25,"f":[[x,y,w,h,confidence],...]}
// مختصات نسبی (۰ تا ۱) با مبدأ بالا-چپ؛ زمان همان زمان ویدیو است.
// ساخت: swiftc -O -parse-as-library -swift-version 5 facetrack.swift -o bin/facetrack (موتور خودش می‌سازد)
import AVFoundation
import CoreGraphics
import Foundation
import Vision

func r4(_ x: Double) -> Double { (x * 10000).rounded() / 10000 }

@main
struct FaceTrack {
    static func main() async {
        let args = CommandLine.arguments
        guard args.count >= 2 else {
            fputs("usage: facetrack <video> [fps]\n", stderr)
            exit(2)
        }
        let fps = args.count > 2 ? (Double(args[2]) ?? 4) : 4
        let asset = AVURLAsset(url: URL(fileURLWithPath: args[1]))
        do {
            let dur = try await asset.load(.duration).seconds
            let gen = AVAssetImageGenerator(asset: asset)
            gen.appliesPreferredTrackTransform = true
            gen.maximumSize = CGSize(width: 720, height: 720)
            let tol = CMTime(seconds: 0.06, preferredTimescale: 600)
            gen.requestedTimeToleranceBefore = tol
            gen.requestedTimeToleranceAfter = tol
            let out = FileHandle.standardOutput
            var t = 0.0
            while t < dur {
                let (img, actual) = try await gen.image(at: CMTime(seconds: t, preferredTimescale: 600))
                let req = VNDetectFaceRectanglesRequest()
                try VNImageRequestHandler(cgImage: img, options: [:]).perform([req])
                let faces: [[Double]] = (req.results ?? []).map { o in
                    let b = o.boundingBox   // مبدأ Vision پایین-چپ است
                    return [r4(Double(b.minX)), r4(1 - Double(b.maxY)), r4(Double(b.width)), r4(Double(b.height)), r4(Double(o.confidence))]
                }
                let line = try JSONSerialization.data(withJSONObject: ["t": r4(actual.seconds), "f": faces])
                out.write(line)
                out.write("\n".data(using: .utf8)!)
                t += 1.0 / fps
            }
        } catch {
            fputs("facetrack error: \(error)\n", stderr)
            exit(1)
        }
    }
}
