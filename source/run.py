import torch
import os
from argparse import ArgumentParser
from pathlib import Path
from datetime import datetime

import source.utility as util
from source.codellama import CodeLlamaModel
from source.codet5 import CodeT5Model
from source.preprocess import load_repairllama_dataset, load_dataset_from_fixme
import source.evaluate as eva

dash_line = "=" * 50

# Setup logger
log = util.get_logger()

config = util.load_config()
log.info(dash_line)
log.info(f"Logging at: {util.log_filename}")
log.info(dash_line)


# Clears the memory cache
torch.cuda.empty_cache()

# Optionally, you can also use this to clear the CUDA memory allocator
torch.cuda.reset_max_memory_allocated()
torch.cuda.reset_max_memory_cached()


config["device"] = torch.device(
    "cuda" if torch.cuda.is_available() else "cpu").type

log.info(f"Using available device: {config['device']}")

# os.environ["TOKENIZERS_PARALLELISM"] = "false"


def get_run_id(config, model_type):
    if config['debug_mode']:
        run_id = model_type + "-Debug"
    else:
        run_id = model_type + \
            str(config['fine_tuning']['num_train_epochs']) + 'epoch-' + \
            datetime.now().strftime("%Y%m%d-%H%M%S")
    config['fine_tuning']['output_dir'] = os.path.join(
        config['fine_tuning']['output_dir'], run_id)
    return config, run_id


if __name__ == "__main__":

    parser = ArgumentParser(
        description="Code Language Models on Generating Security Fixes")

    parser.add_argument('--base_model', type=str, help='Base model to use')
    parser.add_argument('--dataset_use', type=str,  help='Dataset to use')
    parser.add_argument('--debug_mode', action='store_true', help='Debug mode')

    args = parser.parse_args()
    # Update the config with the command line arguments
    config["base_model"] = args.base_model if args.base_model else config["base_model"]
    config["dataset_use"] = args.dataset_use if args.dataset_use else config["dataset_use"]
    config["debug_mode"] = args.debug_mode if args.debug_mode else config["debug_mode"]

    log.info(f"Using base model: {config['base_model']}")
    log.info(f"Using dataset: {config['dataset_use']}")
    log.info(f"Debug mode: {config['debug_mode']}")
    log.info(f"Config: {config}")

    # Load the dataset
    if config["dataset_use"].lower() == "repairllama":
        dataset = load_repairllama_dataset()
    elif config["dataset_use"].lower() == "fixme":
        dataset = load_dataset_from_fixme()
    else:
        raise ValueError("Invalid config['dataset_use'] value!")

    # Load the CodeLlama model or the CodeT5 model
    if 'codellama' in str(config['base_model']).lower():
        config['model_type'] = 'codellama'
    elif 'codet5' in str(config['base_model']).lower():
        config['model_type'] = 'codet5'
    else:
        raise ValueError(f"Invalid model name: {config['base_model']}")

    config, run_id = get_run_id(config, config["model_type"])

    if config['model_type'] == 'codellama':
        code_llama = CodeLlamaModel(config, log)
        model, instruct_model, tokenizer = code_llama.run_codellama(dataset)

    elif config['model_type'] == 'codet5':
        code_t5 = CodeT5Model(config, log)
        model, instruct_model, tokenizer = code_t5.run_codet5(dataset)
    else:
        raise ValueError(f"Invalid model name: {config['base_model']}")

    log.info(dash_line)
    log.info(f"Model loaded successfully: {config['base_model']}")
    log.info(dash_line)

    # result_csv = util.log_dir / f"result-{util.run_id}.csv"
    result_csv = os.path.join(
        config['fine_tuning']['output_dir'], f"result-{run_id}.csv")

    if config["debug_mode"]:
        test_dataset = dataset["test"].shuffle(seed=42).select(range(3))
    else:
        test_dataset = dataset["test"]

    log.info("Generating test patches...")
    results = eva.generate_fixes(
        model,
        instruct_model,
        tokenizer,
        test_dataset,
        result_csv,
    )
    # empty the cache
    del model
    del instruct_model
    torch.cuda.empty_cache()

    log.info("Evaluating the models...")

    eva.evaluate_rouge(results)

    eva.evaluate_bleu(results)
