import json
from functools import singledispatch
import os
import numpy as np
import torch
from dataset_utils import (
    get_ailerons_dataset,
    get_LSAT_dataset,
    get_red_wine_dataset,
    get_synthetic_data,
)
from global_perturbation import perturbation_experiment
from sklearn.preprocessing import StandardScaler


@singledispatch
def to_serializable(val):
    """Used by default."""
    return str(val)


@to_serializable.register(np.float32)
def ts_float32(val):
    """Used if *val* is an instance of numpy.float32."""
    return np.float64(val)


# Standardization for non synthetic datasets
def standardize_output(data):
    data["y_train"] = data["y_train"].reshape(-1, 1)
    data["y_test"] = data["y_test"].reshape(-1, 1)
    data["y_val"] = data["y_val"].reshape(-1, 1)

    scaler = StandardScaler()
    data["y_train"] = scaler.fit_transform(data["y_train"]).flatten()
    data["y_test"] = scaler.transform(data["y_test"]).flatten()
    data["y_val"] = scaler.transform(data["y_val"]).flatten()

    return data


def write_to_json(object, filename):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(object, f, ensure_ascii=False, indent=4, default=to_serializable)


def main():
    torch.set_float32_matmul_precision("medium")
    datasets = ["synthetic", "synthetic_mixed_5"] #["synthetic_mixed_5", "synthetic", "red_wine", "ailerons", "lsat"]
    methods = ["varx_ig", "varx_lrp", "varx", "clue", "infoshap"]
    if not os.path.exists("results/global_perturbation"):
        os.makedirs("results/global_perturbation")
    for run_id in range(12):
        for dataset in datasets:
            if "synthetic" in dataset: 
                data = get_synthetic_data(
                    41500,
                    70,
                    5,
                    0 if dataset == "synthetic" else int(dataset.split("_")[2]),
                    n_samples_train=25000,  # 32000,
                    n_samples_val=15000,  # 8000,
                    n_samples_test=1500,
                )

                out_perturb = perturbation_experiment(
                    **data, epsilons=[1], top_k=3, explain_methods=methods
                )

                write_to_json(
                    {"perturb": out_perturb},
                    f"results/global_perturbation/{dataset}_out_perturbation_global_{run_id}.json",
                )
            else:
                for repeat in [1]:
                    if dataset == "red_wine":
                        data = get_red_wine_dataset()
                    elif dataset == "ailerons":
                        data = get_ailerons_dataset()
                    elif dataset == "lsat":
                        data = get_LSAT_dataset()

                    data["x_train"] = np.repeat(data["x_train"], repeat, axis=0)
                    data["y_train"] = np.repeat(data["y_train"], repeat, axis=0)

                    data = standardize_output(data)
                    out_perturb = perturbation_experiment(
                        **data, epsilons=[1], top_k=3, small_model=False
                    )
                    
                    write_to_json(
                        {"perturb": out_perturb},
                        f"results/global_perturbation/{dataset}_{repeat}_out_perturbation_global_{run_id}.json",
                    )
    print("Done")


if __name__ == "__main__":
    main()
