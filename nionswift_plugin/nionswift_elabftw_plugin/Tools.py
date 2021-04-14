def edit_body_line(input_str, elab_manager):
    
    output_str = input_str

    ## Convert line breaks to HTML paragraph tags
    output_str = output_str.replace('\r\n', '\n').replace('\n', '<p>')

    ## This block replaces '#{int}' by a hyperlink within eLabFTW   
    if output_str.find('#') != -1:

        input_str_list = output_str.split('#')
        for i in range(1, len(input_str_list)):
            str_to_be_parsed = input_str_list[i]
    
            N_integer_digits = 0
            while str_to_be_parsed[:N_integer_digits+1].isdigit() and N_integer_digits <= len(str_to_be_parsed):
                N_integer_digits += 1
            
            if N_integer_digits > 0:
                elabftw_item_id = int(str_to_be_parsed[:N_integer_digits])
            
                try:
                    elabftw_item_dict = elab_manager.get_item(elabftw_item_id)
                    hyperlink_text = "[" + elabftw_item_dict['category'] + "]" + " " + elabftw_item_dict['title']
                    html_open_tag = "<a href='database.php?mode=view&amp;id=" + str(elabftw_item_id) + "'>"
                    html_end_tag = "</a>"
                except:
                    hyperlink_text = "(Item " + str(elabftw_item_id) + " was not found in database)"
                    html_open_tag, html_end_tag = "", ""
            
                input_str_list[i] = html_open_tag + hyperlink_text + html_end_tag + input_str_list[i][N_integer_digits:]
                    
        output_str = ''
        for x in input_str_list:
            output_str += x
    
    ## (Next code block)
    pass
    
    #print(output_str) #dev# for debugging
    return output_str