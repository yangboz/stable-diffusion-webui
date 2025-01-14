# This file is part of stable-diffusion-webui (https://github.com/sd-webui/stable-diffusion-webui/).

# Copyright 2022 sd-webui team.
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# ---------------------------------------------------------------------------------------------------------------------------------------------------
"""
CLIP Interrogator made by @pharmapsychotic modified to work with our WebUI.

# CLIP Interrogator by @pharmapsychotic 
Twitter: https://twitter.com/pharmapsychotic
Github: https://github.com/pharmapsychotic/clip-interrogator

Description:
What do the different OpenAI CLIP models see in an image? What might be a good text prompt to create similar images using CLIP guided diffusion
or another text to image model? The CLIP Interrogator is here to get you answers!

Please consider buying him a coffee via [ko-fi](https://ko-fi.com/pharmapsychotic) or following him on [twitter](https://twitter.com/pharmapsychotic).

And if you're looking for more Ai art tools check out my [Ai generative art tools list](https://pharmapsychotic.com/tools.html).

"""
# ---------------------------------------------------------------------------------------------------------------------------------------------------

# base webui import and utils.
from sd_utils import *

# streamlit imports

# streamlit components section
import streamlit_nested_layout

# other imports

import clip
import open_clip
import gc
import os
import pandas as pd
#import requests
import torch
from PIL import Image
from torchvision import transforms
from torchvision.transforms.functional import InterpolationMode
from ldm.models.blip import blip_decoder

# end of imports
# ---------------------------------------------------------------------------------------------------------------

device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
blip_image_eval_size = 512
#blip_model_url = 'https://storage.googleapis.com/sfr-vision-language-research/BLIP/models/model*_base_caption.pth'
server_state["clip_models"] = {}
server_state["preprocesses"] = {}

def load_blip_model():
    print("Loading BLIP Model")
    st.session_state["log_message"].code("Loading BLIP Model", language='')

    if "blip_model" not in server_state:
        with server_state_lock['blip_model']:
            server_state["blip_model"] = blip_decoder(pretrained="models/blip/model__base_caption.pth",
                                                        image_size=blip_image_eval_size, vit='base', med_config="configs/blip/med_config.json")
            
            server_state["blip_model"] = server_state["blip_model"].eval()
            
            #if not st.session_state["defaults"].general.optimized:
            server_state["blip_model"] = server_state["blip_model"].to(device).half()
            
            print("BLIP Model Loaded")
            st.session_state["log_message"].code("BLIP Model Loaded", language='')
    else:
        print("BLIP Model already loaded")
        st.session_state["log_message"].code("BLIP Model Already Loaded", language='')

    #return server_state["blip_model"]


#
def artstation_links():
    """Find and save every artstation link for the first 500 pages of the explore page."""
    # collecting links to the list()
    links = []
    
    with open('data/img2txt/artstation_links.txt', 'w') as f:
        for page_num in range(1,500):
            response = requests.get(f'https://www.artstation.com/api/v2/community/explore/projects/trending.json?page={page_num}&dimension=all&per_page=100').text
            # open json response
            data = json.loads(response)
            
            # loopinh through json response
            for result in data['data']:
                # still looping and grabbing url's
                url = result['url']
                links.append(url)
                # writing each link on the new line (\n)
                f.write(f'{url}\n')  
    return links
#
def artstation_users():
    """Get all the usernames and full name of the users on the first 500 pages of artstation explore page."""
    # collect username and full name
    artists = []
    
    # opening a .txt file
    with open('data/img2txt/artstation_artists.txt', 'w') as f:
        for page_num in range(1,500):
            response = requests.get(f'https://www.artstation.com/api/v2/community/explore/projects/trending.json?page={page_num}&dimension=all&per_page=100').text
            # open json response
            data = json.loads(response)
    
    
            # loopinh through json response
            for item in data['data']:
                #print (item['user'])
                username = item['user']['username']
                full_name = item['user']['full_name']
    
                # still looping and grabbing url's
                artists.append(username)
                artists.append(full_name)
                # writing each link on the new line (\n)
                f.write(f'{slugify(username)}\n')
                f.write(f'{slugify(full_name)}\n')
    
    return artists

def generate_caption(pil_image):

    load_blip_model()
    
    gpu_image = transforms.Compose([  # type: ignore
        transforms.Resize((blip_image_eval_size, blip_image_eval_size), interpolation=InterpolationMode.BICUBIC),  # type: ignore
        transforms.ToTensor(),  # type: ignore
        transforms.Normalize((0.48145466, 0.4578275, 0.40821073), (0.26862954, 0.26130258, 0.27577711))  # type: ignore
    ])(pil_image).unsqueeze(0).to(device).half()

    with torch.no_grad():
        caption = server_state["blip_model"].generate(gpu_image, sample=False, num_beams=3, max_length=20, min_length=5)

    #print (caption)
    return caption[0]

def load_list(filename):
    with open(filename, 'r', encoding='utf-8', errors='replace') as f:
        items = [line.strip() for line in f.readlines()]
        return items

def rank(model, image_features, text_array, top_count=1):
    top_count = min(top_count, len(text_array))
    text_tokens = clip.tokenize([text for text in text_array]).cuda()
    with torch.no_grad():
        text_features = model.encode_text(text_tokens).float()
    text_features /= text_features.norm(dim=-1, keepdim=True)

    similarity = torch.zeros((1, len(text_array))).to(device)
    for i in range(image_features.shape[0]):
        similarity += (100.0 * image_features[i].unsqueeze(0) @ text_features.T).softmax(dim=-1)
    similarity /= image_features.shape[0]

    top_probs, top_labels = similarity.cpu().topk(top_count, dim=-1)
    return [(text_array[top_labels[0][i].numpy()], (top_probs[0][i].numpy()*100)) for i in range(top_count)]


def clear_cuda():
    torch.cuda.empty_cache()
    gc.collect()


def batch_rank(model, image_features, text_array, batch_size=st.session_state["defaults"].img2txt.batch_size):
    batch_size = min(batch_size, len(text_array))
    batch_count = int(len(text_array) / batch_size)
    batches = [text_array[i*batch_size:(i+1)*batch_size] for i in range(batch_count)]
    ranks = []
    for batch in batches:
        ranks += rank(model, image_features, batch)
    return ranks

def interrogate(image, models):

    #server_state["blip_model"] = 
    load_blip_model()
    
    print("Generating Caption")
    st.session_state["log_message"].code("Generating Caption", language='')
    caption = generate_caption(image)

    if st.session_state["defaults"].general.optimized:
        del server_state["blip_model"]
        clear_cuda()

    print("Caption Generated")
    st.session_state["log_message"].code("Caption Generated", language='')

    if len(models) == 0:
        print(f"\n\n{caption}")
        return

    table = []
    bests = [[('', 0)]]*5

    print("Ranking Text")
    
    #if "clip_model" in server_state:
        #print (server_state["clip_model"])
        
    #print (st.session_state["log_message"])
        
    for model_name in models:
        with torch.no_grad(), torch.autocast('cuda', dtype=torch.float16):
            print(f"Interrogating with {model_name}...")
            st.session_state["log_message"].code(f"Interrogating with {model_name}...", language='')
            
            if model_name not in server_state["clip_models"]:
                if not st.session_state["defaults"].img2txt.keep_all_models_loaded:
                    model_to_delete = []
                    for model in server_state["clip_models"]:
                        if model != model_name:
                            model_to_delete.append(model)
                    for model in model_to_delete:
                        del server_state["clip_models"][model]
                        del server_state["preprocesses"][model]
                        clear_cuda()
                if model_name == 'ViT-H-14':
                    server_state["clip_models"][model_name], _, server_state["preprocesses"][model_name] = open_clip.create_model_and_transforms(model_name, pretrained='laion2b_s32b_b79k', cache_dir='models/clip')
                elif model_name == 'ViT-g-14':
                    server_state["clip_models"][model_name], _, server_state["preprocesses"][model_name] = open_clip.create_model_and_transforms(model_name, pretrained='laion2b_s12b_b42k', cache_dir='models/clip')
                else:
                    server_state["clip_models"][model_name], server_state["preprocesses"][model_name] = clip.load(model_name, device=device, download_root='models/clip')
                server_state["clip_models"][model_name] = server_state["clip_models"][model_name].cuda().eval()
            
            images = server_state["preprocesses"][model_name](image).unsqueeze(0).cuda()
                    
            
            image_features = server_state["clip_models"][model_name].encode_image(images).float()
                
            image_features /= image_features.norm(dim=-1, keepdim=True)

            if st.session_state["defaults"].general.optimized:
                clear_cuda()
                
            ranks = []
            ranks.append(batch_rank(server_state["clip_models"][model_name], image_features, server_state["mediums"]))
            ranks.append(batch_rank(server_state["clip_models"][model_name], image_features, ["by "+artist for artist in server_state["artists"]]))
            ranks.append(batch_rank(server_state["clip_models"][model_name], image_features, server_state["trending_list"]))
            ranks.append(batch_rank(server_state["clip_models"][model_name], image_features, server_state["movements"]))
            ranks.append(batch_rank(server_state["clip_models"][model_name], image_features, server_state["flavors"]))
            # ranks.append(batch_rank(server_state["clip_models"][model_name], image_features, server_state["genres"]))
            # ranks.append(batch_rank(server_state["clip_models"][model_name], image_features, server_state["styles"]))
            # ranks.append(batch_rank(server_state["clip_models"][model_name], image_features, server_state["techniques"]))
            # ranks.append(batch_rank(server_state["clip_models"][model_name], image_features, server_state["subjects"]))
            # ranks.append(batch_rank(server_state["clip_models"][model_name], image_features, server_state["colors"]))
            # ranks.append(batch_rank(server_state["clip_models"][model_name], image_features, server_state["moods"]))
            # ranks.append(batch_rank(server_state["clip_models"][model_name], image_features, server_state["themes"]))
            # ranks.append(batch_rank(server_state["clip_models"][model_name], image_features, server_state["keywords"]))

            for i in range(len(ranks)):
                confidence_sum = 0
                for ci in range(len(ranks[i])):
                    confidence_sum += ranks[i][ci][1]
                if confidence_sum > sum(bests[i][t][1] for t in range(len(bests[i]))):
                    bests[i] = ranks[i]

            row = [model_name]
            for r in ranks:
                row.append(', '.join([f"{x[0]} ({x[1]:0.1f}%)" for x in r]))

            table.append(row)

            if st.session_state["defaults"].general.optimized:
                del server_state["clip_models"][model_name]
                gc.collect()

    # for i in range(len(st.session_state["uploaded_image"])):
    st.session_state["prediction_table"][st.session_state["processed_image_count"]].dataframe(pd.DataFrame(
        table, columns=["Model", "Medium", "Artist", "Trending", "Movement", "Flavors"]))

    flaves = ', '.join([f"{x[0]}" for x in bests[4]])
    medium = bests[0][0][0]
    if caption.startswith(medium):
        st.session_state["text_result"][st.session_state["processed_image_count"]].code(
            f"\n\n{caption} {bests[1][0][0]}, {bests[2][0][0]}, {bests[3][0][0]}, {flaves}", language="")
    else:
        st.session_state["text_result"][st.session_state["processed_image_count"]].code(
            f"\n\n{caption}, {medium} {bests[1][0][0]}, {bests[2][0][0]}, {bests[3][0][0]}, {flaves}", language="")

    #
    print("Finished Interrogating.")
    st.session_state["log_message"].code("Finished Interrogating.", language="")
#


def img2txt():
    data_path = "data/"

    server_state["artists"] = load_list(os.path.join(data_path, 'img2txt', 'artists.txt'))
    server_state["flavors"] = load_list(os.path.join(data_path, 'img2txt', 'flavors.txt'))
    server_state["mediums"] = load_list(os.path.join(data_path, 'img2txt', 'mediums.txt'))
    server_state["movements"] = load_list(os.path.join(data_path, 'img2txt', 'movements.txt'))
    server_state["sites"] = load_list(os.path.join(data_path, 'img2txt', 'sites.txt'))
    # server_state["genres"] = load_list(os.path.join(data_path, 'img2txt', 'genres.txt'))
    # server_state["styles"] = load_list(os.path.join(data_path, 'img2txt', 'styles.txt'))
    # server_state["techniques"] = load_list(os.path.join(data_path, 'img2txt', 'techniques.txt'))
    # server_state["subjects"] = load_list(os.path.join(data_path, 'img2txt', 'subjects.txt'))

    server_state["trending_list"] = [site for site in server_state["sites"]]
    server_state["trending_list"].extend(["trending on "+site for site in server_state["sites"]])
    server_state["trending_list"].extend(["featured on "+site for site in server_state["sites"]])
    server_state["trending_list"].extend([site+" contest winner" for site in server_state["sites"]])

    #image_path_or_url = "https://i.redd.it/e2e8gimigjq91.jpg"

    models = []

    if st.session_state["ViT-L/14"]:
        models.append('ViT-L/14')
    if st.session_state["ViT-H-14"]:
        models.append('ViT-H-14')
    if st.session_state["ViT-g-14"]:
        models.append('ViT-g-14')
        
    if st.session_state["ViTB32"]:
        models.append('ViT-B/32')
    if st.session_state['ViTB16']:
        models.append('ViT-B/16')  
        
    if st.session_state["ViTL14_336px"]:
        models.append('ViT-L/14@336px')
    if st.session_state["RN101"]:
        models.append('RN101')
    if st.session_state["RN50"]:
        models.append('RN50')
    if st.session_state["RN50x4"]:
        models.append('RN50x4')
    if st.session_state["RN50x16"]:
        models.append('RN50x16')
    if st.session_state["RN50x64"]:
        models.append('RN50x64')    

    # if str(image_path_or_url).startswith('http://') or str(image_path_or_url).startswith('https://'):
        #image = Image.open(requests.get(image_path_or_url, stream=True).raw).convert('RGB')
    # else:
        #image = Image.open(image_path_or_url).convert('RGB')

    #thumb = st.session_state["uploaded_image"].image.copy()
    #thumb.thumbnail([blip_image_eval_size, blip_image_eval_size])
    # display(thumb)

    st.session_state["processed_image_count"] = 0

    for i in range(len(st.session_state["uploaded_image"])):

        interrogate(st.session_state["uploaded_image"][i].pil_image, models=models)
        # increase counter.
        st.session_state["processed_image_count"] += 1
#


def layout():
    #set_page_title("Image-to-Text - Stable Diffusion WebUI")
    #st.info("Under Construction. :construction_worker:")

    with st.form("img2txt-inputs"):
        st.session_state["generation_mode"] = "img2txt"

        # st.write("---")
        # creating the page layout using columns
        col1, col2 = st.columns([1, 4], gap="large")

        with col1:
            #url = st.text_area("Input Text","")
            #url = st.text_input("Input Text","", placeholder="A corgi wearing a top hat as an oil painting.")
            #st.subheader("Input Image")
            st.session_state["uploaded_image"] = st.file_uploader('Input Image', type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

            with st.expander("CLIP models", expanded=True):
                st.session_state["ViT-L/14"] = st.checkbox("ViT-L/14", value=True, help="ViT-L/14 model.")
                st.session_state["ViT-H-14"] = st.checkbox("ViT-H-14", value=False, help="ViT-H-14 model.")
                st.session_state["ViT-g-14"] = st.checkbox("ViT-g-14", value=False, help="ViT-g-14 model.")

            
                
            with st.expander("Others"):
                st.info("For DiscoDiffusion and JAX enable all the same models here as you intend to use when generating your images.")   
                
                st.session_state["ViTL14_336px"] = st.checkbox("ViTL14_336px", value=False, help="ViTL14_336px model.")
                st.session_state["ViTB16"] = st.checkbox("ViTB16", value=False, help="ViTB16 model.")
                st.session_state["ViTB32"] = st.checkbox("ViTB32", value=False, help="ViTB32 model.")
                st.session_state["RN50"] = st.checkbox("RN50", value=False, help="RN50 model.")
                st.session_state["RN50x4"] = st.checkbox("RN50x4", value=False, help="RN50x4 model.")
                st.session_state["RN50x16"] = st.checkbox("RN50x16", value=False, help="RN50x16 model.")
                st.session_state["RN50x64"] = st.checkbox("RN50x64", value=False, help="RN50x64 model.")
                st.session_state["RN101"] = st.checkbox("RN101", value=False, help="RN101 model.")      
                
            #
            # st.subheader("Logs:")

            st.session_state["log_message"] = st.empty()
            st.session_state["log_message"].code('', language="")

        with col2:
            st.subheader("Image")

            refresh = st.form_submit_button("Refresh", help='Refresh the image preview to show your uploaded image instead of the default placeholder.')

            if st.session_state["uploaded_image"]:
                #print (type(st.session_state["uploaded_image"]))
                # if len(st.session_state["uploaded_image"]) == 1:
                st.session_state["input_image_preview"] = []
                st.session_state["input_image_preview_container"] = []
                st.session_state["prediction_table"] = []
                st.session_state["text_result"] = []

                for i in range(len(st.session_state["uploaded_image"])):
                    st.session_state["input_image_preview_container"].append(i)
                    st.session_state["input_image_preview_container"][i] = st.empty()

                    with st.session_state["input_image_preview_container"][i].container():
                        col1_output, col2_output = st.columns([2, 10], gap="medium")
                        with col1_output:
                            st.session_state["input_image_preview"].append(i)
                            st.session_state["input_image_preview"][i] = st.empty()
                            st.session_state["uploaded_image"][i].pil_image = Image.open(st.session_state["uploaded_image"][i]).convert('RGB')

                            st.session_state["input_image_preview"][i].image(st.session_state["uploaded_image"][i].pil_image, use_column_width=True, clamp=True)

                    with st.session_state["input_image_preview_container"][i].container():

                        with col2_output:

                            st.session_state["prediction_table"].append(i)
                            st.session_state["prediction_table"][i] = st.empty()
                            st.session_state["prediction_table"][i].table()

                            st.session_state["text_result"].append(i)
                            st.session_state["text_result"][i] = st.empty()
                            st.session_state["text_result"][i].code("", language="")

            else:
                #st.session_state["input_image_preview"].code('', language="")
                st.image("images/streamlit/img2txt_placeholder.png", clamp=True)

        #
        # Every form must have a submit button, the extra blank spaces is a temp way to align it with the input field. Needs to be done in CSS or some other way.
        # generate_col1.title("")
        # generate_col1.title("")
        generate_button = st.form_submit_button("Generate!")

    if generate_button:
        # if model, pipe, RealESRGAN or GFPGAN is in st.session_state remove the model and pipe form session_state so that they are reloaded.
        if "model" in server_state and st.session_state["defaults"].general.optimized:
            del server_state["model"]
        if "pipe" in server_state and st.session_state["defaults"].general.optimized:
            del server_state["pipe"]
        if "RealESRGAN" in server_state and st.session_state["defaults"].general.optimized:
            del server_state["RealESRGAN"]
        if "GFPGAN" in server_state and st.session_state["defaults"].general.optimized:
            del server_state["GFPGAN"]

        # run clip interrogator
        img2txt()
