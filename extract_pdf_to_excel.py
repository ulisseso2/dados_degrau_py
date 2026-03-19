import pdfplumber
import pandas as pd
import re  # Adicionado para limpeza de texto

def extract_names_and_ids(pdf_path, output_excel):
    # Open the PDF file
    with pdfplumber.open(pdf_path) as pdf:
        data = []
        
        # Iterate through all pages
        for page in pdf.pages:
            text = page.extract_text()
            
            # Split text into lines
            lines = text.split("\n")
            
            # Process each line to extract names and IDs
            for line in lines:
                # Remover números extras e limpar o texto
                line = re.sub(r"\d{1,2}\s", "", line)  # Remove números no início da linha
                
                # Assuming the format is "Name - ID"
                parts = line.split("-")
                if len(parts) == 2:
                    name = parts[0].strip()
                    registration_id = parts[1].strip()
                    data.append({"Name": name, "Registration ID": registration_id})

    # Convert to DataFrame
    df = pd.DataFrame(data)

    # Save to Excel
    df.to_excel(output_excel, index=False)

if __name__ == "__main__":
    # Path to the PDF file
    pdf_path = "aprovados/tjsp_aprovados.pdf"  # Caminho atualizado para o arquivo correto

    # Output Excel file
    output_excel = "aprovados/lista_aprovados.xlsx"

    # Extract data and save to Excel
    extract_names_and_ids(pdf_path, output_excel)
    print(f"Planilha salva em: {output_excel}")