param (
    [string]$source,
    [string]$destination
)

$ErrorActionPreference = "Stop"

write ("Source : {0}" -f $source)
write ("Destination : {0}" -f $destination)

If(Test-path $destination) {
    write ("Ensuring existing archive is removed : {0}" -f $destination)
    try {
        Remove-item $destination -Force
    } catch {
        throw ("Could not remove the existing archive '{0}'. It is probably open in " +
               "Explorer or an archive viewer; close it and rebuild. Underlying error: {1}" `
               -f $destination, $_.Exception.Message)
    }
    if (Test-Path $destination) {
        throw ("Existing archive '{0}' is still present after removal." -f $destination)
    }
    write ("Existing archive removed successfully")
}

Add-Type -assembly "system.io.compression.filesystem"

$EncoderClass=@"
  public class FixedEncoder : System.Text.UTF8Encoding {
    public FixedEncoder() : base(true) { }
    public override byte[] GetBytes(string s) {
      s = s.Replace("\\", "/");
      return base.GetBytes(s);
    }
  }
"@
Add-Type -TypeDefinition $EncoderClass

$Encoder = New-Object FixedEncoder
# Args: source, destination, compressionLevel (0 = Optimal), includeBaseDirectory, encoding.
# includeBaseDirectory MUST be $false so Blender manifest is in the root
[io.compression.zipfile]::CreateFromDirectory($source, $destination, 0, $false, $Encoder)

if (-not (Test-Path $destination)) {
    throw ("Archive '{0}' was not created." -f $destination)
}
write ("File successfully written: {0}" -f $destination)
