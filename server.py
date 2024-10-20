""" A reworking of the BirdNet server, but using flask
as the basic webserver instead.
"""
from flask import Flask
from flask import request
import tempfile
import os
import json
import analyze
import config as cfg
import species
import utils


app = Flask(__name__)



def resultPooling(lines: list[str], num_results=5, pmode="avg"):
    """Parses the results into list of (species, score).

    Args:
        lines: List of result scores.
        num_results: The number of entries to be returned.
        pmode: Decides how the score for each species is computed.
               If "max" used the maximum score for the species,
               if "avg" computes the average score per species.

    Returns:
        A List of (species, score).
    """
    # Parse results
    results = {}
    assert(len(lines) > 1)

    # Ignore the first line as that's the table header
    for line in lines[1:]:
        # Hardcoded positions here! Tsk
        d = line.split("\t")
        species = d[7].replace(", ", "_")
        score = float(d[9])

        if species not in results:
            results[species] = []

        results[species].append(score)

    # Compute score for each species
    for species in results:
        if pmode == "max":
            results[species] = max(results[species])
        else:
            results[species] = sum(results[species]) / len(results[species])

    # Sort results
    results = sorted(results.items(), key=lambda x: x[1], reverse=True)

    return results[:num_results]

@app.post("/analyze")
def analysis():
    # Load eBird codes, labels
    cfg.CODES = analyze.loadCodes()
    cfg.LABELS = utils.readLines(cfg.LABELS_FILE)
    cfg.TRANSLATED_LABELS = cfg.LABELS


    # Start by creating a temporary working directory
    with tempfile.TemporaryDirectory() as tmpdirname:
        f = request.files['audio']
        audio_path = tmpdirname + "/audio.wav"
        f.save(audio_path)
        assert(os.path.exists(audio_path))
        meta = json.loads(request.form["meta"])

        # Now do the analysis proper
        # This cfg thing is quite terrible and really needs to go!
        try:
            cfg.OUTPUT_PATH = tmpdirname
            cfg.INPUT_PATH = tmpdirname
            cfg.FILE_STORAGE_PATH = tmpdirname
            cfg.MIN_CONFIDENCE = 0.0

            #if "lat" in meta and "lon" in meta:
            #    cfg.LATITUDE = float(meta["lat"])
            #    cfg.LONGITUDE = float(meta["lon"])
            #else:
            cfg.LATITUDE = -1
            cfg.LONGITUDE = -1

            cfg.WEEK = int(meta.get("week", -1))
            cfg.SIG_OVERLAP = max(0.0, min(2.9, float(meta.get("overlap", 0.0))))
            cfg.SIGMOID_SENSITIVITY = max(0.5, min(1.0 - (float(meta.get("sensitivity", 1.0)) - 1.0), 1.5))
            cfg.LOCATION_FILTER_THRESHOLD = max(0.01, min(0.99, float(meta.get("sf_thresh", 0.03))))


            # Set species list
            cfg.SPECIES_LIST_FILE = None
            cfg.SPECIES_LIST = species.getSpeciesList(cfg.LATITUDE, cfg.LONGITUDE, cfg.WEEK, cfg.LOCATION_FILTER_THRESHOLD)
          
            # Analyze file
            success = analyze.analyzeFile((audio_path, cfg.getConfig()))

            # Parse results
            if success:   
                # Results file - matches the wav file name in the first part
                results_file = tmpdirname + "/audio.BirdNET.selection.table.txt"

                # Print all the files we have
                #for root, dirs, files in os.walk(tmpdirname):
                #    path = root.split(os.sep)
                #    print((len(path) - 1) * '---', os.path.basename(root))
                #    for file in files:
                #        print(len(path) * '---', file)

                with open(results_file, "r") as f:
                    lines = f.readlines()
                    pmode = meta.get("pmode", "avg").lower()

                    # Pool results
                    if pmode not in ["avg", "max"]:
                        pmode = "avg"

                    num_results = min(99, max(1, int(meta.get("num_results", 5))))
                    results = resultPooling(lines, num_results, pmode)
                    data = {"msg": "success", "results": results, "meta": meta}

                    print(data)
                
                    return json.dumps(data)
            
            return json.dumps({"msg": "Could not peform analysis."})
        
        except Exception as e:
            print(e)
            return json.dumps({"msg": "Error during analysis."})


@app.route("/")
def hello_world():
    return "<p>Hello, BirdNet!</p>"