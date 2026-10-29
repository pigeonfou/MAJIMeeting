"""Runtime-side setup checks; a file avoids Windows PowerShell 5 command quoting."""
import argparse
import getpass
import os


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['check', 'download', 'validate'])
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    parser.add_argument('--model')
    args = parser.parse_args()
    os.environ.update(PYANNOTE_METRICS_ENABLED='false', OTEL_SDK_DISABLED='true',
                      HF_HUB_DISABLE_TELEMETRY='1')
    if args.action == 'check':
        import torch
        from pyannote.audio import Pipeline  # noqa: F401
        ready = torch.cuda.is_available()
        print('Runtime importe, CUDA disponible:', ready, flush=True)
        if args.device == 'cuda' and not ready:
            raise SystemExit('CUDA indisponible : verifiez le pilote NVIDIA ou choisissez CPU.')
    else:
        if not args.model:
            parser.error('--model est requis')
        if args.action == 'download':
            from huggingface_hub import snapshot_download
            snapshot_download('pyannote/speaker-diarization-community-1',
                              token=getpass.getpass('Jeton Hugging Face (lecture, non conserve): '),
                              local_dir=args.model)
        else:
            os.environ['HF_HUB_OFFLINE'] = '1'
            from pyannote.audio import Pipeline
            Pipeline.from_pretrained(args.model)
            print('Modele local charge hors ligne', flush=True)


if __name__ == '__main__':
    main()
