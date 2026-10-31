"""Disable self-update in the pinned SurfingTile 7.0.0 APK decoded by Apktool.

Usage: python disable_tile_updates.py ORIGINAL.apk DECODED_DIRECTORY
Only the APK with the pinned digest is supported. Rebuild and sign separately.
"""
import hashlib
from pathlib import Path
import re
import sys

APK_SHA256 = '721546b0222c3d60b898fa7a951d6c789250dcb2c04d41273fb62b0b9b06d064'


def replace_method(text, signature, body):
    pattern = r'^' + re.escape(signature) + r'\n.*?^\.end method$'
    result, count = re.subn(pattern, lambda _: signature + '\n' + body.strip() + '\n.end method',
                            text, flags=re.M | re.S)
    if count != 1:
        raise ValueError('Expected exactly one method: ' + signature)
    return result


def patch(apk, decoded):
    if hashlib.sha256(apk.read_bytes()).hexdigest() != APK_SHA256:
        raise ValueError('Unsupported APK digest; refusing to patch an unknown build')
    smali = decoded / 'smali'
    changes = {}
    # Preserve the completion callback on the main thread without doing a request.
    text = (smali / 'hg.smali').read_text(encoding='utf-8')
    if 'const-class v15, Lcom/github/surfing/data/AppUpdateResponse;' not in text:
        raise ValueError('Update checker fingerprint does not match')
    changes[smali / 'hg.smali'] = replace_method(text, '.method private final k()V', '''
    .locals 6
    iget-object v0, p0, Lhg;->w:Ljava/lang/Object;
    check-cast v0, Lhp5;
    const/4 v3, 0x0
    iput-boolean v3, v0, Lhp5;->d:Z
    iget-object v1, p0, Lhg;->y:Ljava/lang/Object;
    new-instance v2, Ldj;
    const-string v4, ""
    const/4 v5, 0x4
    invoke-direct {v2, v1, v3, v4, v5}, Ldj;-><init>(Ljava/lang/Object;ZLjava/lang/Object;B)V
    iget-object v0, v0, Lhp5;->b:Landroid/os/Handler;
    invoke-virtual {v0, v2}, Landroid/os/Handler;->post(Ljava/lang/Runnable;)Z
    return-void
''')
    text = (smali / 'hp5.smali').read_text(encoding='utf-8')
    for signature, body in [
        ('.method public static b(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;',
         '.locals 1\n    const/4 v0, 0x0\n    return-object v0'),
        ('.method public final c(Ljava/io/File;Ljava/lang/String;)Z',
         '.locals 1\n    const/4 v0, 0x0\n    return v0'),
        ('.method public final e(Lcom/github/surfing/ui/ExtraActivity;Ljava/io/File;)V',
         '.locals 0\n    return-void'),
    ]:
        text = replace_method(text, signature, body)
    changes[smali / 'hp5.smali'] = text
    # Keep a clear disabled page instead of an endless checking indicator.
    text = (smali / 'pp5.smali').read_text(encoding='utf-8')
    text = replace_method(text, '.method public final f(Lcom/github/surfing/ui/ExtraActivity;Landroid/os/Bundle;)V', '''
    .locals 2
    iput-object p1, p0, Lpp5;->v:Lcom/github/surfing/ui/ExtraActivity;
    const-string v0, "SurfingTile - updates disabled"
    invoke-virtual {p1, v0}, Lew;->v(Ljava/lang/String;)V
    new-instance v0, Landroid/widget/TextView;
    invoke-direct {v0, p1}, Landroid/widget/TextView;-><init>(Landroid/content/Context;)V
    const-string v1, "此版本已移除应用更新检查与下载。"
    invoke-virtual {v0, v1}, Landroid/widget/TextView;->setText(Ljava/lang/CharSequence;)V
    const/16 v1, 0x11
    invoke-virtual {v0, v1}, Landroid/widget/TextView;->setGravity(I)V
    invoke-virtual {p1, v0}, Landroid/app/Activity;->setContentView(Landroid/view/View;)V
    return-void
''')
    # These lifecycle/check hooks must not access the removed update controls.
    for signature in ['.method public final B()V', '.method public final c()V',
                      '.method public final j(Landroid/os/Bundle;)V']:
        text = replace_method(text, signature, '.locals 0\n    return-void')
    changes[smali / 'pp5.smali'] = text
    metadata = decoded / 'apktool.yml'
    yml = metadata.read_text(encoding='utf-8')
    if 'versionName: 7.0.0\n' not in yml:
        raise ValueError('Unexpected version metadata')
    changes[metadata] = yml.replace('versionName: 7.0.0\n', 'versionName: 7.0.0-no-update\n', 1)
    for path, content in changes.items():
        path.write_text(content, encoding='utf-8', newline='\n')
    print('Patched update checker, download paths and update page; signing is still required.')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: disable_tile_updates.py ORIGINAL.apk DECODED_DIRECTORY')
    patch(Path(sys.argv[1]), Path(sys.argv[2]))
