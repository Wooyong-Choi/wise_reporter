from modules.base_module import BaseModule
from modules.image_selection.image_selection_2019_v2 import *
from keras.models import load_model
from elasticsearch import Elasticsearch

class ImageSelectionModule(BaseModule):
    def __init__(self, out_path):        
        self.out_path = out_path
        self.vggModel = load_model('modules/image_selection/weight_best.hdf') ###
        self.es = Elasticsearch("155.230.34.145:9200")
        print("weight_best loaded")
        self.g = tf.Graph()
        with self.g.as_default():
            self.text_input = tf.placeholder(dtype=tf.string, shape=[None])
            self.embed = hub.Module("https://tfhub.dev/google/universal-sentence-encoder-multilingual/1")
            self.embedded_text = self.embed(self.text_input)
            self.init_op = tf.group([tf.global_variables_initializer(), tf.tables_initializer()])
        self.g.finalize()
        print("graph defined")
        
    def process_data(self, query, image_save_path, download_limit = 50):
        es_query = {'query':{'match':{'keyword':query}}}
        res = self.es.search(index='image', body=es_query)
        if res['hits']['total']['value'] == 0:
            output = None
        else:
            output = res['hits']['hits'][0]['_source']
        path_cached = ('./downloads')
        check_query_exist = os.listdir(path_cached)
        if query not in check_query_exist:  # case 1 : if query is new - download images & caption from google, scouter caching(url, caption), local caching(image path, caption)
            print("query is new")
            if type(query) is list:
                topic = []
                topic.append(query[0].replace('/','_'))
            if type(query) is not list:
                query = query.replace('/','_')
                topic = []
                topic.append(query)
            print("query pre-processed")
            try_iter = 1
            while try_iter < 5: # handling VGG16 input error, no image found in google
                try:
                    dict_image, file_list, image_list, caption_list = image_caption_downloader(topic, download_limit)
                    temp_f = file_list[0] 
                    break
                except IndexError:
                    print("try image download again")
                    try_iter = try_iter + 1
            print("image and caption downloaded")

            # --- scouter caching ---
            if output == None:
                image_dict = { 'keyword': query, 'image': dict_image[query][0], 'caption': dict_image[query][1]} 
                res = self.es.index(index='image', body=image_dict)

            # --- local caching ---
            try:
                if not(os.path.isdir('localcache')):
                    os.makedirs(os.path.join('localcache'))
            except OSError as e:
                if e.errno != errno.EEXIST:
                    print("Failed to create directory!!!!!")
                    raise
            localcache_name = 'localcache/%s.txt'%(query)
            if try_iter != 5: # wychoi: 이미지 검색 안되면 caching 안함
                with open(localcache_name, 'w') as f:
                    for imgfile in image_list:
                        f.write("%s\n"%imgfile)
                    for captionfile in caption_list:
                        f.write("%s\n"%captionfile)

        else: # case 2 : if query is used before - use local cached data
            print("query already used before")
            if type(query) is list:
                topic = []
                topic.append(query[0].replace('/','_'))
            if type(query) is not list:
                query = query.replace('/','_')
                topic = []
                topic.append(query)
            localcache_name = 'localcache/%s.txt'%(query)
            file_list, image_list, caption_list = image_caption_get(localcache_name, download_limit)
        if len(file_list) == 0:
            return False

        nongraph_image_list, nongraph_caption_list = VGG_classifier(file_list, image_list, caption_list, self.vggModel) ###
        final_image = semantic_similarity_module(self.g, self.init_op, self.embedded_text, self.text_input, topic, nongraph_image_list, nongraph_caption_list) ####
        imgsave_path = image_save_path # path to save final recommended image
        temp_image = Image.open(final_image)
        temp_image = temp_image.convert('RGB')
        temp_image.save('%s'%(imgsave_path))
        #shutil.rmtree('./downloads/%s'%(final_image.split('/')[2]), ignore_errors=True)

