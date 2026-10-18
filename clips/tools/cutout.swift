// Lift the people out of a photo with macOS Vision (the same model as "Copy Subject"), no downloads.
// usage: cutout <in.png> <out.png> [x y]   -> out.png: the input with everything but the subjects transparent;
//        with x y (0..1 from the top left) only the subject under that point (e.g. a face), not someone's shoulder
import AppKit
import CoreImage
import Vision

let args = CommandLine.arguments
guard args.count == 3 || args.count == 5, let src = CIImage(contentsOf: URL(fileURLWithPath: args[1])) else {
    FileHandle.standardError.write("usage: cutout <in.png> <out.png>\n".data(using: .utf8)!)
    exit(2)
}
let request = VNGenerateForegroundInstanceMaskRequest()
let handler = VNImageRequestHandler(ciImage: src)
do {
    try handler.perform([request])
    guard let result = request.results?.first else { exit(3) }
    var which = result.allInstances
    if args.count == 5, let x = Double(args[3]), let y = Double(args[4]) {
        let m = result.instanceMask
        CVPixelBufferLockBaseAddress(m, .readOnly)
        let w = CVPixelBufferGetWidth(m), h = CVPixelBufferGetHeight(m)
        let row = CVPixelBufferGetBytesPerRow(m)
        let base = CVPixelBufferGetBaseAddress(m)!.assumingMemoryBound(to: UInt8.self)
        let id = Int(base[min(h - 1, Int(y * Double(h))) * row + min(w - 1, Int(x * Double(w)))])
        CVPixelBufferUnlockBaseAddress(m, .readOnly)
        if id > 0 { which = IndexSet(integer: id) }
    }
    let buf = try result.generateMaskedImage(ofInstances: which, from: handler,
                                             croppedToInstancesExtent: false)
    let ci = CIImage(cvPixelBuffer: buf)
    let ctx = CIContext()
    guard let cg = ctx.createCGImage(ci, from: ci.extent) else { exit(4) }
    let rep = NSBitmapImageRep(cgImage: cg)
    try rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: args[2]))
} catch {
    FileHandle.standardError.write("\(error)\n".data(using: .utf8)!)
    exit(1)
}
